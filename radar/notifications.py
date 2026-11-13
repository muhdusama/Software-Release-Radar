from __future__ import annotations

import email.utils
import http.client
import json
import logging
import smtplib
import sqlite3
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from .db import connect, get_settings, transaction, utcnow
from .security_policy import _is_loopback_host, insecure_integrations_allowed
from .secrets_store import decrypt_secret
from .version import APP_VERSION
from .http_client import open_http
from .system_channels import (
    SYSTEM_CHANNEL_KEYS,
    SYSTEM_CHANNEL_LABELS,
    SYSTEM_CHANNELS,
    channel_configured,
    enabled_system_channels,
    send_system_channel,
)

LOGGER = logging.getLogger("software_release_radar.notifications")

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


class ChannelDisabledError(NotificationError):
    """The provider is switched off in Settings, so the delivery is skipped."""


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
        raise ChannelDisabledError("SMTP notifications are disabled.")
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
            elif cfg["security"] != "ssl" and not (
                _is_loopback_host(str(cfg["host"])) or insecure_integrations_allowed()
            ):
                raise smtplib.SMTPException(
                    "SMTP delivery requires STARTTLS or implicit TLS. "
                    "Set ALLOW_INSECURE_INTEGRATIONS=true only for an explicitly "
                    "accepted trusted-network exception."
                )
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
        raise ChannelDisabledError("Pushover notifications are disabled.")
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
        with open_http(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise NotificationError(
            f"Pushover returned HTTP {exc.code}: {detail}"
        ) from exc
    except (
        OSError,
        http.client.HTTPException,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
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


MAX_DELIVERY_ATTEMPTS = 5
RETRY_BACKOFF_SECONDS = 300
PENDING_BATCH_LIMIT = 50
STALE_EVENT_DAYS = 7
_TERMINAL = ("sent", "skipped")


def _parse_time(value: str | None) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _delivery_action(prior, now: datetime) -> str:
    """Classify an earlier delivery row as ``done``, ``wait`` or ``send``.

    A failed row is retried after ``RETRY_BACKOFF_SECONDS * attempts`` and is
    terminal once ``MAX_DELIVERY_ATTEMPTS`` real attempts have been made.
    """
    if prior is None:
        return "send"
    status, attempts, last_attempt_at = prior
    if status in _TERMINAL or attempts >= MAX_DELIVERY_ATTEMPTS:
        return "done"
    last = _parse_time(last_attempt_at)
    if last and now < last + timedelta(seconds=RETRY_BACKOFF_SECONDS * attempts):
        return "wait"
    return "send"


def _record_delivery(
    *,
    event_id: int,
    user_id: int,
    channel: str,
    status: str,
    error: str | None,
) -> None:
    attempted = 0 if status == "skipped" else 1
    now = utcnow()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO notification_deliveries
                (event_id, user_id, channel, status, error, sent_at,
                 attempts, last_attempt_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, user_id, channel) DO UPDATE SET
                status = excluded.status,
                error = excluded.error,
                sent_at = excluded.sent_at,
                attempts = attempts + excluded.attempts,
                last_attempt_at = excluded.last_attempt_at
            """,
            (event_id, user_id, channel, status, error, now, attempted, now),
        )


def _record_system_delivery(
    *, event_id: int, channel: str, status: str, error: str | None
) -> None:
    attempted = 0 if status == "skipped" else 1
    now = utcnow()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO system_notification_deliveries
                (event_id, channel, status, error, sent_at, attempts, last_attempt_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, channel) DO UPDATE SET
                status = excluded.status,
                error = excluded.error,
                sent_at = excluded.sent_at,
                attempts = attempts + excluded.attempts,
                last_attempt_at = excluded.last_attempt_at
            """,
            (event_id, channel, status, error, now, attempted, now),
        )


def _failure_text(exc: Exception) -> str:
    return (str(exc) or type(exc).__name__)[:1000]


def dispatch_release_notifications(
    event_ids: list[int] | None = None,
) -> dict[str, int]:
    """Dispatch each event through global, personal and per-software policy.

    Muted deliveries are persisted as skipped. Re-enabling notifications later
    therefore does not create a surprise backlog of previously muted releases.
    Failed deliveries are retried with a bounded attempt count. Every delivery
    is isolated, so one failing channel or user cannot abort the others.
    ``events.notified_at`` is set once every delivery for the event is
    terminal: sent, skipped, or failed with the attempts exhausted.

    System channels (webhook, ntfy, Gotify) deliver once per event and follow
    the preferences of the first active administrator.
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
        prior_user = {
            (int(row["event_id"]), int(row["user_id"]), str(row["channel"])): (
                str(row["status"]), int(row["attempts"] or 0), row["last_attempt_at"],
            )
            for row in conn.execute(
                """
                SELECT event_id, user_id, channel, status, attempts, last_attempt_at
                  FROM notification_deliveries
                """
            )
        }
        prior_system = {
            (int(row["event_id"]), str(row["channel"])): (
                str(row["status"]), int(row["attempts"] or 0), row["last_attempt_at"],
            )
            for row in conn.execute(
                """
                SELECT event_id, channel, status, attempts, last_attempt_at
                  FROM system_notification_deliveries
                """
            )
        }
        setting = conn.execute(
            "SELECT value FROM settings WHERE key = 'notifications_enabled'"
        ).fetchone()

    system_enabled = _as_bool(setting["value"] if setting else "1")
    try:
        system_channels = enabled_system_channels()
    except Exception:
        LOGGER.warning("System notification channel settings could not be read.")
        system_channels = []
    admin = next((u for u in users if u["role"] == "admin"), None)
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    now = datetime.now(timezone.utc)

    def settle(prior, status: str, error: str | None, record, **ids) -> bool:
        """Record one outcome; return True when the delivery is still open."""
        record(status=status, error=error, **ids)
        counts[status] += 1
        attempts = (prior[1] if prior else 0) + (0 if status == "skipped" else 1)
        return status == "failed" and attempts < MAX_DELIVERY_ATTEMPTS

    for event in events:
        title, body, release_url = _release_message(event)
        tracker_id = int(event["tracker_id"])
        event_id = int(event["id"])
        open_deliveries = False

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
                key = (event_id, user_id, channel)
                prior = prior_user.get(key)
                action = _delivery_action(prior, now)
                if action == "wait":
                    open_deliveries = True
                    continue
                if action == "done":
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
                    except ChannelDisabledError as exc:
                        status, error = "skipped", str(exc)
                    except Exception as exc:  # isolate each delivery
                        status, error = "failed", _failure_text(exc)

                try:
                    open_deliveries |= settle(
                        prior, status, error, _record_delivery,
                        event_id=event_id, user_id=user_id, channel=channel,
                    )
                except Exception:
                    LOGGER.exception("Could not record a notification delivery.")
                    open_deliveries = True

        if system_channels:
            admin_mode = (
                preferences.get((int(admin["id"]), tracker_id), "inherit")
                if admin else "inherit"
            )
            if admin_mode not in NOTIFICATION_MODES:
                admin_mode = "inherit"
            system_allowed, system_reason = _policy_enabled(
                system_enabled=system_enabled,
                user_default_enabled=(
                    bool(int(admin["notifications_enabled"] or 0)) if admin else True
                ),
                mode=admin_mode,
            )
        for channel in system_channels:
            prior = prior_system.get((event_id, channel))
            action = _delivery_action(prior, now)
            if action == "wait":
                open_deliveries = True
                continue
            if action == "done":
                continue
            status, error = "sent", None
            if not system_allowed:
                status, error = "skipped", system_reason
            else:
                try:
                    send_system_channel(channel, event, title, body)
                except Exception as exc:  # isolate each delivery
                    status, error = "failed", _failure_text(exc)
            try:
                open_deliveries |= settle(
                    prior, status, error, _record_system_delivery,
                    event_id=event_id, channel=channel,
                )
            except Exception:
                LOGGER.exception("Could not record a system notification delivery.")
                open_deliveries = True

        if not open_deliveries:
            _mark_event_notified(event_id)

    return counts


def _mark_event_notified(event_id: int) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE events SET notified_at = ? WHERE id = ? AND notified_at IS NULL",
            (utcnow(), event_id),
        )


def close_stale_events() -> None:
    """Close pending events older than ``STALE_EVENT_DAYS`` without sending.

    Upgrading from a version that never set ``notified_at``, or a long outage,
    therefore never floods users with old alerts.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=STALE_EVENT_DAYS)).replace(
        microsecond=0
    ).isoformat()
    with transaction() as conn:
        conn.execute(
            "UPDATE events SET notified_at = ? WHERE notified_at IS NULL AND detected_at < ?",
            (utcnow(), cutoff),
        )


def dispatch_pending_notifications(limit: int = PENDING_BATCH_LIMIT) -> dict[str, int]:
    """Dispatch the oldest pending events, whichever cycle detected them."""
    close_stale_events()
    with connect() as conn:
        ids = [
            int(row["id"])
            for row in conn.execute(
                """
                SELECT id FROM events WHERE notified_at IS NULL
                 ORDER BY detected_at, id LIMIT ?
                """,
                (limit,),
            )
        ]
    if not ids:
        return {"sent": 0, "failed": 0, "skipped": 0}
    return dispatch_release_notifications(ids)


def recent_delivery_failures(limit: int = 20) -> list[dict[str, object]]:
    """Most recent failed deliveries across user and system channels."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.name AS software, d.channel, d.error, d.attempts,
                   d.last_attempt_at AS at, u.username AS recipient
              FROM notification_deliveries d
              JOIN events e ON e.id = d.event_id
              JOIN trackers t ON t.id = e.tracker_id
              JOIN users u ON u.id = d.user_id
             WHERE d.status = 'failed'
            UNION ALL
            SELECT t.name, d.channel, d.error, d.attempts,
                   d.last_attempt_at, 'System'
              FROM system_notification_deliveries d
              JOIN events e ON e.id = d.event_id
              JOIN trackers t ON t.id = e.tracker_id
             WHERE d.status = 'failed'
             ORDER BY at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {**dict(row), "error": str(row["error"] or "")[:200],
         "exhausted": int(row["attempts"] or 0) >= MAX_DELIVERY_ATTEMPTS}
        for row in rows
    ]


def configured_channels() -> list[dict[str, object]]:
    """Which release-alert channels can actually deliver. No secrets are returned."""
    smtp = get_settings(SMTP_KEYS)
    pushover = get_settings(PUSHOVER_KEYS)
    system = get_settings(SYSTEM_CHANNEL_KEYS)
    rows: list[dict[str, object]] = [
        {"name": "Email", "scope": "Per user",
         "enabled": _as_bool(smtp["smtp_enabled"]),
         "configured": bool(smtp["smtp_host"] and smtp["smtp_from_email"])},
        {"name": "Pushover", "scope": "Per user",
         "enabled": _as_bool(pushover["pushover_enabled"]),
         "configured": bool(pushover["pushover_app_token_enc"])},
    ]
    for channel in SYSTEM_CHANNELS:
        rows.append({
            "name": SYSTEM_CHANNEL_LABELS[channel], "scope": "System",
            "enabled": _as_bool(system[f"{channel}_enabled"]),
            "configured": channel_configured(system, channel),
        })
    return rows


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
