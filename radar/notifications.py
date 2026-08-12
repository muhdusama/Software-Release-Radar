from __future__ import annotations

import email.utils
import json
import smtplib
import sqlite3
import ssl
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from .db import connect, get_settings, transaction, utcnow
from .secrets_store import decrypt_secret
from .version import APP_VERSION

SMTP_KEYS = [
    "smtp_enabled",
    "smtp_host",
    "smtp_port",
    "smtp_security",
    "smtp_username",
    "smtp_password_enc",
    "smtp_from_email",
    "smtp_from_name",
    "smtp_timeout",
]
PUSHOVER_KEYS = [
    "pushover_enabled",
    "pushover_app_token_enc",
    "pushover_priority",
    "pushover_sound",
]
NOTIFICATION_MODES = frozenset({"inherit", "on", "off"})
NOTIFICATION_CHANNELS = ("email", "pushover")


class NotificationError(RuntimeError):
    pass


def _as_bool(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table})")
    }


def ensure_notification_preferences() -> None:
    """Install additive global, personal and per-software preference storage."""
    with transaction() as conn:
        if "notifications_enabled" not in _columns(conn, "users"):
            try:
                conn.execute(
                    """
                    ALTER TABLE users
                    ADD COLUMN notifications_enabled INTEGER NOT NULL DEFAULT 1
                    """
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tracker_notification_preferences (
                user_id INTEGER NOT NULL,
                tracker_id INTEGER NOT NULL,
                mode TEXT NOT NULL DEFAULT 'inherit'
                    CHECK (mode IN ('inherit', 'on', 'off')),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, tracker_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (tracker_id) REFERENCES trackers(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_tracker_notification_preferences_tracker
                ON tracker_notification_preferences(tracker_id, user_id);
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO settings (key, value, updated_at)
            VALUES ('notifications_enabled', '1', ?)
            """,
            (utcnow(),),
        )


def smtp_config() -> dict[str, str | int | bool]:
    raw = get_settings(SMTP_KEYS)
    return {
        "enabled": _as_bool(raw["smtp_enabled"]),
        "host": raw["smtp_host"].strip(),
        "port": int(raw["smtp_port"] or 587),
        "security": raw["smtp_security"] or "starttls",
        "username": raw["smtp_username"].strip(),
        "password": decrypt_secret(raw["smtp_password_enc"]),
        "from_email": raw["smtp_from_email"].strip(),
        "from_name": (
            raw["smtp_from_name"].strip() or "Software Release Radar"
        ),
        "timeout": int(raw["smtp_timeout"] or 15),
    }


def send_email(to_email: str, subject: str, body: str) -> None:
    cfg = smtp_config()
    if not cfg["enabled"]:
        raise NotificationError("SMTP notifications are disabled.")
    if not cfg["host"] or not cfg["from_email"]:
        raise NotificationError("SMTP host and From email are required.")
    message = EmailMessage()
    message["From"] = email.utils.formataddr(
        (str(cfg["from_name"]), str(cfg["from_email"]))
    )
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    context = ssl.create_default_context()
    try:
        if cfg["security"] == "ssl":
            server = smtplib.SMTP_SSL(
                str(cfg["host"]),
                int(cfg["port"]),
                timeout=int(cfg["timeout"]),
                context=context,
            )
        else:
            server = smtplib.SMTP(
                str(cfg["host"]),
                int(cfg["port"]),
                timeout=int(cfg["timeout"]),
            )
        with server:
            server.ehlo()
            if cfg["security"] == "starttls":
                server.starttls(context=context)
                server.ehlo()
            if cfg["username"]:
                server.login(str(cfg["username"]), str(cfg["password"]))
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise NotificationError(f"SMTP delivery failed: {exc}") from exc


def pushover_config() -> dict[str, str | int | bool]:
    raw = get_settings(PUSHOVER_KEYS)
    return {
        "enabled": _as_bool(raw["pushover_enabled"]),
        "app_token": decrypt_secret(raw["pushover_app_token_enc"]),
        "priority": int(raw["pushover_priority"] or 0),
        "sound": raw["pushover_sound"].strip() or "pushover",
    }


def send_pushover(
    user_key: str,
    title: str,
    message: str,
    url: str | None = None,
) -> None:
    cfg = pushover_config()
    if not cfg["enabled"]:
        raise NotificationError("Pushover notifications are disabled.")
    if not cfg["app_token"] or not user_key:
        raise NotificationError(
            "Pushover application token and user key are required."
        )
    payload = {
        "token": str(cfg["app_token"]),
        "user": user_key,
        "title": title[:250],
        "message": message[:1024],
        "priority": str(cfg["priority"]),
        "sound": str(cfg["sound"]),
    }
    if url:
        payload["url"] = url[:512]
        payload["url_title"] = "Open release"
    request = urllib.request.Request(
        "https://api.pushover.net/1/messages.json",
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": f"Software-Release-Radar/{APP_VERSION}",
        },
        method="POST",
    )
    try:
        # The request target is the fixed Pushover HTTPS API endpoint.
        with urllib.request.urlopen(request, timeout=15) as response:  # nosec B310
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise NotificationError(
            f"Pushover returned HTTP {exc.code}: {detail}"
        ) from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise NotificationError(f"Pushover delivery failed: {exc}") from exc
    if int(result.get("status", 0)) != 1:
        raise NotificationError(
            "Pushover rejected the message: "
            + "; ".join(result.get("errors") or ["unknown error"])
        )


def _release_message(event) -> tuple[str, str, str | None]:
    release = str(
        event["release_name"] or event["version"] or "New release"
    )
    previous = str(
        event["previous_release_name"] or event["previous_version"] or ""
    ).strip()
    lines = [f"{event['name']}: {release}"]
    if previous:
        lines.append(f"Updated from: {previous}")
    if (
        event["version"]
        and str(event["version"]).casefold() != release.casefold()
    ):
        lines.append(f"Git tag: {event['version']}")
    if event["machine_name"] or event["install_host"]:
        target = event["machine_name"] or event["install_host"]
        installed = (
            event["detected_installed_version"]
            or event["installed_version"]
            or "unknown"
        )
        lines.append(f"Installed on {target}: {installed}")
    if event["tags"]:
        lines.append("Tags: " + str(event["tags"]).replace(",", ", "))
    return (
        f"Software update: {event['name']}",
        "\n".join(lines),
        event["release_url"],
    )


def pending_release_events():
    with connect() as conn:
        return conn.execute(
            """
            SELECT e.*, t.name, t.repository, t.tags, t.machine_name,
                   t.install_host, t.installed_version,
                   t.detected_installed_version
              FROM events e
              JOIN trackers t ON t.id = e.tracker_id
             ORDER BY e.detected_at, e.id
            """
        ).fetchall()


def _policy_enabled(
    *,
    system_enabled: bool,
    user_default_enabled: bool,
    mode: str,
) -> tuple[bool, str | None]:
    if not system_enabled:
        return False, "Notifications are paused by the administrator."
    if mode == "off":
        return False, "Notifications are muted for this software."
    if mode == "on":
        return True, None
    if user_default_enabled:
        return True, None
    return False, "Personal release notifications are paused."


def _record_delivery(
    *,
    event_id: int,
    user_id: int,
    channel: str,
    status: str,
    error: str | None,
) -> None:
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO notification_deliveries
                (event_id, user_id, channel, status, error, sent_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, user_id, channel) DO UPDATE SET
                status = excluded.status,
                error = excluded.error,
                sent_at = excluded.sent_at
            """,
            (event_id, user_id, channel, status, error, utcnow()),
        )


def dispatch_release_notifications(
    event_ids: list[int] | None = None,
) -> dict[str, int]:
    """Dispatch each event through global, personal and per-software policy.

    Muted deliveries are persisted as skipped. Re-enabling notifications later
    therefore does not create a surprise backlog of previously muted releases.
    Failed deliveries remain retryable because only sent and skipped rows are
    treated as complete.
    """
    ensure_notification_preferences()
    params: list[object] = []
    where = ""
    if event_ids:
        placeholders = ",".join("?" for _ in event_ids)
        where = f" WHERE e.id IN ({placeholders})"
        params.extend(event_ids)

    with connect() as conn:
        events = conn.execute(
            """
            SELECT e.*, t.name, t.repository, t.tags, t.machine_name,
                   t.install_host, t.installed_version,
                   t.detected_installed_version
              FROM events e
              JOIN trackers t ON t.id = e.tracker_id
            """
            + where
            + " ORDER BY e.detected_at, e.id",
            params,
        ).fetchall()
        users = conn.execute(
            "SELECT * FROM users WHERE active = 1 ORDER BY id"
        ).fetchall()
        preferences = {
            (int(row["user_id"]), int(row["tracker_id"])): str(row["mode"])
            for row in conn.execute(
                """
                SELECT user_id, tracker_id, mode
                  FROM tracker_notification_preferences
                """
            ).fetchall()
        }
        existing = {
            (int(row["event_id"]), int(row["user_id"]), str(row["channel"]))
            for row in conn.execute(
                """
                SELECT event_id, user_id, channel
                  FROM notification_deliveries
                 WHERE status IN ('sent', 'skipped')
                """
            )
        }
        setting = conn.execute(
            "SELECT value FROM settings WHERE key = 'notifications_enabled'"
        ).fetchone()

    system_enabled = _as_bool(setting["value"] if setting else "1")
    counts = {"sent": 0, "failed": 0, "skipped": 0}

    for event in events:
        title, body, release_url = _release_message(event)
        tracker_id = int(event["tracker_id"])
        for user in users:
            user_id = int(user["id"])
            mode = preferences.get((user_id, tracker_id), "inherit")
            if mode not in NOTIFICATION_MODES:
                mode = "inherit"
            policy_enabled, policy_reason = _policy_enabled(
                system_enabled=system_enabled,
                user_default_enabled=bool(
                    int(user["notifications_enabled"] or 0)
                ),
                mode=mode,
            )

            for channel in NOTIFICATION_CHANNELS:
                key = (int(event["id"]), user_id, channel)
                if key in existing:
                    continue

                status = "sent"
                error: str | None = None
                if not policy_enabled:
                    status, error = "skipped", policy_reason
                elif channel == "email" and not int(user["notify_email"] or 0):
                    status, error = "skipped", "Email notifications are disabled."
                elif (
                    channel == "pushover"
                    and not int(user["notify_pushover"] or 0)
                ):
                    status, error = (
                        "skipped",
                        "Pushover notifications are disabled.",
                    )
                else:
                    try:
                        if channel == "email":
                            if not user["email"]:
                                status, error = (
                                    "skipped",
                                    "User has no email address.",
                                )
                            else:
                                suffix = f"\n\n{release_url}" if release_url else ""
                                send_email(
                                    str(user["email"]),
                                    title,
                                    body + suffix,
                                )
                        else:
                            user_key = decrypt_secret(
                                user["pushover_user_key_enc"]
                            )
                            if not user_key:
                                status, error = (
                                    "skipped",
                                    "User has no Pushover key.",
                                )
                            else:
                                send_pushover(
                                    user_key,
                                    title,
                                    body,
                                    release_url,
                                )
                    except (NotificationError, RuntimeError) as exc:
                        status, error = "failed", str(exc)[:1000]

                _record_delivery(
                    event_id=int(event["id"]),
                    user_id=user_id,
                    channel=channel,
                    status=status,
                    error=error,
                )
                counts[status] += 1

    return counts


def notification_smoke_payload() -> dict[str, str | None]:
    return {
        "title": "Software Release Radar notification smoke test",
        "message": (
            "Deterministic notification pipeline smoke test. No software was "
            "installed, updated, restarted, or changed."
        ),
        "url": None,
    }


def notification_smoke_test(*, send: bool = False) -> dict[str, object]:
    ensure_notification_preferences()
    payload = notification_smoke_payload()
    with connect() as conn:
        users = conn.execute(
            "SELECT * FROM users WHERE active = 1 ORDER BY id"
        ).fetchall()

    recipients: list[dict[str, object]] = []
    for user in users:
        channels: list[str] = []
        if int(user["notify_email"] or 0):
            channels.append("email")
        if int(user["notify_pushover"] or 0):
            channels.append("pushover")
        if channels:
            recipients.append(
                {
                    "user_id": int(user["id"]),
                    "username": str(user["username"]),
                    "channels": channels,
                }
            )

    if not send:
        return {
            "mode": "dry-run",
            "payload": payload,
            "recipient_count": len(recipients),
            "recipients": recipients,
        }

    counts = {"sent": 0, "failed": 0, "skipped": 0}
    results: list[dict[str, object]] = []
    for user in users:
        if int(user["notify_email"] or 0):
            status, error = "sent", None
            if not user["email"]:
                status, error = "skipped", "User has no email address."
            else:
                try:
                    send_email(
                        str(user["email"]),
                        str(payload["title"]),
                        str(payload["message"]),
                    )
                except (NotificationError, RuntimeError) as exc:
                    status, error = "failed", str(exc)[:1000]
            counts[status] += 1
            results.append(
                {
                    "user_id": int(user["id"]),
                    "channel": "email",
                    "status": status,
                    "error": error,
                }
            )

        if int(user["notify_pushover"] or 0):
            status, error = "sent", None
            user_key = decrypt_secret(user["pushover_user_key_enc"])
            if not user_key:
                status, error = "skipped", "User has no Pushover key."
            else:
                try:
                    send_pushover(
                        user_key,
                        str(payload["title"]),
                        str(payload["message"]),
                        None,
                    )
                except (NotificationError, RuntimeError) as exc:
                    status, error = "failed", str(exc)[:1000]
            counts[status] += 1
            results.append(
                {
                    "user_id": int(user["id"]),
                    "channel": "pushover",
                    "status": status,
                    "error": error,
                }
            )

    return {
        "mode": "sent",
        "payload": payload,
        "counts": counts,
        "results": results,
    }
