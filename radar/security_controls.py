from __future__ import annotations

import hashlib
import hmac
import logging
import os
import queue
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)

from .auth import token_digest
from .db import connect, get_setting, get_settings, transaction, utcnow
from .notifications import NotificationError, send_email
from .security_policy import (
    trusted_application_origin,
    validate_credential_url,
    validate_smtp_transport,
)

_LOGGER = logging.getLogger(__name__)
_EMAIL_QUEUE: queue.Queue[tuple[str, str, str]] = queue.Queue(maxsize=64)
_EMAIL_THREAD: threading.Thread | None = None
_EMAIL_THREAD_LOCK = threading.Lock()

_AI_USER_WINDOW_SECONDS = 10 * 60
_AI_IP_WINDOW_SECONDS = 60 * 60
_AI_DAY_SECONDS = 24 * 60 * 60
_AI_DEFAULT_USER_WINDOW_LIMIT = 10
_AI_DEFAULT_USER_DAY_LIMIT = 50
_AI_DEFAULT_IP_WINDOW_LIMIT = 30
_AI_DEFAULT_PER_USER_CONCURRENCY = 1
_AI_DEFAULT_GLOBAL_CONCURRENCY = 4
_AI_DEFAULT_LEASE_SECONDS = 180
_AI_DEFAULT_QUESTION_CHARS = 4_000
_AI_ANALYSIS_CACHE_MINUTES = 15
_AI_MESSAGES_PER_CONVERSATION = 200
_AI_ANALYSES_PER_TRACKER = 20


class AIUsageLimitError(RuntimeError):
    pass


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _csrf_is_valid() -> bool:
    expected = str(session.get("csrf_token") or "")
    supplied = str(request.form.get("csrf_token") or "")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _email_worker() -> None:
    while True:
        to_email, subject, body = _EMAIL_QUEUE.get()
        try:
            send_email(to_email, subject, body)
        except (NotificationError, RuntimeError, OSError):
            _LOGGER.warning("Asynchronous password-reset email delivery failed.")
        finally:
            _EMAIL_QUEUE.task_done()


def _ensure_email_worker() -> None:
    global _EMAIL_THREAD
    with _EMAIL_THREAD_LOCK:
        if _EMAIL_THREAD is not None and _EMAIL_THREAD.is_alive():
            return
        _EMAIL_THREAD = threading.Thread(
            target=_email_worker,
            name="radar-password-reset-email",
            daemon=True,
        )
        _EMAIL_THREAD.start()


def _enqueue_email(to_email: str, subject: str, body: str) -> bool:
    _ensure_email_worker()
    try:
        _EMAIL_QUEUE.put_nowait((to_email, subject, body))
        return True
    except queue.Full:
        _LOGGER.warning("Password-reset email queue is full.")
        return False


def _minimum_reset_delay(started: float) -> None:
    configured = os.environ.get("PASSWORD_RESET_MIN_SECONDS", "0.35")
    try:
        minimum = float(configured)
    except ValueError:
        minimum = 0.35
    minimum = max(0.1, min(2.0, minimum))
    jitter = secrets.randbelow(51) / 1000
    remaining = minimum + jitter - (time.monotonic() - started)
    if remaining > 0:
        time.sleep(remaining)


def _install_security_tables() -> None:
    now = utcnow()
    with transaction() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_security_counters (
                key TEXT PRIMARY KEY,
                requests INTEGER NOT NULL DEFAULT 0,
                expires_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ai_security_leases (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_ai_security_counter_expiry
                ON ai_security_counters(expires_at);
            CREATE INDEX IF NOT EXISTS idx_ai_security_lease_expiry
                ON ai_security_leases(expires_at, user_id);
            """
        )
        conn.execute("DELETE FROM ai_security_counters WHERE expires_at <= ?", (now,))
        conn.execute("DELETE FROM ai_security_leases WHERE expires_at <= ?", (now,))


def _rate_key(secret_key: str, namespace: str, value: str) -> str:
    digest = hmac.new(
        secret_key.encode("utf-8"),
        f"{namespace}:{value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{namespace}:{digest}"


def _window(now: datetime, seconds: int) -> tuple[int, str]:
    epoch = int(now.timestamp())
    start = epoch - (epoch % seconds)
    expiry = datetime.fromtimestamp(start + seconds, timezone.utc).replace(
        microsecond=0
    )
    return start, expiry.isoformat()


def _acquire_ai_lease(app: Flask, user_id: int, remote: str) -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_text = now.isoformat()
    secret_key = str(app.secret_key or "")
    if not secret_key:
        raise RuntimeError("Application secret key is required for Assistant limits.")

    user_window_limit = _int_env(
        "AI_USER_10_MINUTE_LIMIT",
        _AI_DEFAULT_USER_WINDOW_LIMIT,
        minimum=1,
        maximum=500,
    )
    user_day_limit = _int_env(
        "AI_USER_DAILY_LIMIT",
        _AI_DEFAULT_USER_DAY_LIMIT,
        minimum=1,
        maximum=10_000,
    )
    ip_window_limit = _int_env(
        "AI_IP_HOURLY_LIMIT",
        _AI_DEFAULT_IP_WINDOW_LIMIT,
        minimum=1,
        maximum=2_000,
    )
    per_user_concurrency = _int_env(
        "AI_USER_CONCURRENCY_LIMIT",
        _AI_DEFAULT_PER_USER_CONCURRENCY,
        minimum=1,
        maximum=20,
    )
    global_concurrency = _int_env(
        "AI_GLOBAL_CONCURRENCY_LIMIT",
        _AI_DEFAULT_GLOBAL_CONCURRENCY,
        minimum=1,
        maximum=100,
    )
    lease_seconds = _int_env(
        "AI_REQUEST_LEASE_SECONDS",
        _AI_DEFAULT_LEASE_SECONDS,
        minimum=30,
        maximum=900,
    )

    user_window, user_window_expiry = _window(now, _AI_USER_WINDOW_SECONDS)
    ip_window, ip_window_expiry = _window(now, _AI_IP_WINDOW_SECONDS)
    day_window, day_expiry = _window(now, _AI_DAY_SECONDS)
    counters = [
        (
            _rate_key(secret_key, "ai-user-10m", f"{user_id}:{user_window}"),
            user_window_limit,
            user_window_expiry,
            "Assistant request limit reached. Try again later.",
        ),
        (
            _rate_key(secret_key, "ai-user-day", f"{user_id}:{day_window}"),
            user_day_limit,
            day_expiry,
            "Daily Assistant request limit reached.",
        ),
        (
            _rate_key(secret_key, "ai-ip-hour", f"{remote}:{ip_window}"),
            ip_window_limit,
            ip_window_expiry,
            "Assistant request limit reached for this network address.",
        ),
    ]
    lease_id = secrets.token_urlsafe(24)
    lease_expiry = (now + timedelta(seconds=lease_seconds)).isoformat()

    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM ai_security_counters WHERE expires_at <= ?", (now_text,))
        conn.execute("DELETE FROM ai_security_leases WHERE expires_at <= ?", (now_text,))

        user_active = int(
            conn.execute(
                "SELECT COUNT(*) FROM ai_security_leases WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]
        )
        global_active = int(
            conn.execute("SELECT COUNT(*) FROM ai_security_leases").fetchone()[0]
        )
        if user_active >= per_user_concurrency:
            raise AIUsageLimitError(
                "An Assistant request is already running for this account."
            )
        if global_active >= global_concurrency:
            raise AIUsageLimitError(
                "The Assistant is busy. Try again after another request finishes."
            )

        for key, limit, _, message in counters:
            row = conn.execute(
                "SELECT requests FROM ai_security_counters WHERE key = ?",
                (key,),
            ).fetchone()
            if row and int(row["requests"]) >= limit:
                raise AIUsageLimitError(message)

        for key, _, expires_at, _ in counters:
            conn.execute(
                """
                INSERT INTO ai_security_counters (key, requests, expires_at, updated_at)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    requests = requests + 1,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (key, expires_at, now_text),
            )
        conn.execute(
            """
            INSERT INTO ai_security_leases (id, user_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (lease_id, user_id, lease_expiry, now_text),
        )
        conn.commit()
        return lease_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _release_ai_lease(lease_id: str | None) -> None:
    if not lease_id:
        return
    with transaction() as conn:
        conn.execute("DELETE FROM ai_security_leases WHERE id = ?", (lease_id,))


def _recent_analysis(user_id: int, tracker):
    cutoff = (
        datetime.now(timezone.utc) - timedelta(minutes=_AI_ANALYSIS_CACHE_MINUTES)
    ).replace(microsecond=0).isoformat()
    installed = tracker["detected_installed_version"] or tracker["installed_version"]
    release = tracker["current_version"]
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM ai_analyses
             WHERE user_id = ?
               AND tracker_id = ?
               AND installed_version IS ?
               AND release_version IS ?
               AND created_at >= ?
             ORDER BY id DESC
             LIMIT 1
            """,
            (user_id, tracker["id"], installed, release, cutoff),
        ).fetchone()


def _prune_ai_history(user_id: int, tracker_id: int) -> None:
    with transaction() as conn:
        conversations = conn.execute(
            "SELECT id FROM ai_conversations WHERE user_id = ? AND tracker_id = ?",
            (user_id, tracker_id),
        ).fetchall()
        for conversation in conversations:
            conn.execute(
                """
                DELETE FROM ai_messages
                 WHERE conversation_id = ?
                   AND id NOT IN (
                       SELECT id FROM ai_messages
                        WHERE conversation_id = ?
                        ORDER BY id DESC
                        LIMIT ?
                   )
                """,
                (
                    conversation["id"],
                    conversation["id"],
                    _AI_MESSAGES_PER_CONVERSATION,
                ),
            )
        conn.execute(
            """
            DELETE FROM ai_analyses
             WHERE user_id = ?
               AND tracker_id = ?
               AND id NOT IN (
                   SELECT id FROM ai_analyses
                    WHERE user_id = ? AND tracker_id = ?
                    ORDER BY id DESC
                    LIMIT ?
               )
            """,
            (
                user_id,
                tracker_id,
                user_id,
                tracker_id,
                _AI_ANALYSES_PER_TRACKER,
            ),
        )


def _ai_error(message: str, status: int = 429):
    if request.endpoint == "assistant_run":
        return jsonify(ok=False, error=message), status
    flash(message, "error")
    tracker_id = request.form.get("tracker_id", type=int)
    target = url_for("assistant", tracker_id=tracker_id) if tracker_id else url_for("assistant")
    return redirect(target)


def _cached_analysis_response(analysis):
    if request.endpoint == "assistant_run":
        return jsonify(
            ok=True,
            action="analyse",
            answer=analysis["content"],
            model=analysis["model"],
            analysis_id=int(analysis["id"]),
            cached=True,
            message="Recent release comparison reused.",
        )
    flash("A recent comparison for this release was reused.", "info")
    return redirect(url_for("assistant", tracker_id=analysis["tracker_id"]))


def _validate_settings_submission():
    if request.endpoint != "settings" or request.method != "POST":
        return None
    if g.user is None or str(g.user["role"]) != "admin" or not _csrf_is_valid():
        return None

    section = request.form.get("section", "general")
    try:
        if section == "general":
            trusted_application_origin(
                request.form.get("app_base_url", ""),
                required=False,
            )
        elif section == "smtp":
            enabled = bool(request.form.get("smtp_enabled"))
            if enabled:
                trusted_application_origin(
                    get_setting("app_base_url", ""),
                    required=True,
                )
                security = request.form.get("smtp_security", "starttls")
                saved = get_settings(["smtp_password_enc"])
                password_present = bool(
                    request.form.get("smtp_password")
                    or (
                        saved.get("smtp_password_enc")
                        and not request.form.get("clear_smtp_password")
                    )
                )
                validate_smtp_transport(
                    request.form.get("smtp_host", ""),
                    security,
                    username_present=bool(request.form.get("smtp_username", "").strip()),
                    password_present=password_present,
                )
        elif section == "portainer":
            if request.form.get("portainer_enabled"):
                saved = get_settings(["portainer_api_token_enc"])
                token_present = bool(
                    request.form.get("portainer_api_token")
                    or (
                        saved.get("portainer_api_token_enc")
                        and not request.form.get("clear_portainer_api_token")
                    )
                )
                base_url = request.form.get("portainer_base_url", "").strip()
                if base_url:
                    validate_credential_url(
                        base_url,
                        credential_present=token_present,
                        label="Portainer base URL",
                    )
        elif section == "openai":
            if request.form.get("openai_enabled"):
                saved = get_settings(["openai_api_key_enc"])
                key_present = bool(
                    request.form.get("openai_api_key")
                    or (
                        saved.get("openai_api_key_enc")
                        and not request.form.get("clear_openai_api_key")
                    )
                )
                base_url = request.form.get("openai_base_url", "").strip()
                if base_url:
                    validate_credential_url(
                        base_url,
                        credential_present=key_present,
                        label="OpenAI-compatible base URL",
                    )
            timeout = int(request.form.get("openai_timeout", "120"))
            max_tokens = int(request.form.get("openai_max_tokens", "1800"))
            if timeout > 120:
                raise ValueError("Assistant timeout must not exceed 120 seconds.")
            if max_tokens > 4096:
                raise ValueError("Maximum Assistant response tokens must not exceed 4096.")
    except (TypeError, ValueError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("settings", section=section))
    return None


def install_security_controls(app: Flask) -> None:
    """Install fixes for validated authentication, AI, and transport findings."""
    _install_security_tables()

    original_forgot_password = app.view_functions.get("forgot_password")
    if original_forgot_password is None:
        raise RuntimeError("forgot_password endpoint is required before security controls.")

    @wraps(original_forgot_password)
    def secure_forgot_password():
        if request.method != "POST":
            return original_forgot_password()

        started = time.monotonic()
        if not _csrf_is_valid():
            return original_forgot_password()

        identity = request.form.get("identity", "").strip()
        token = secrets.token_urlsafe(40)
        digest = token_digest(token)
        with connect() as conn:
            user = conn.execute(
                """
                SELECT * FROM users
                 WHERE active = 1
                   AND (username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE)
                """,
                (identity, identity),
            ).fetchone()

        try:
            base_url = trusted_application_origin(
                get_setting("app_base_url", ""),
                required=True,
            )
        except ValueError:
            base_url = None

        if user and user["email"] and base_url:
            now = datetime.now(timezone.utc)
            expires = (now + timedelta(hours=1)).replace(microsecond=0).isoformat()
            with transaction() as conn:
                conn.execute(
                    """
                    UPDATE password_reset_tokens
                       SET used_at = ?
                     WHERE user_id = ? AND used_at IS NULL
                    """,
                    (utcnow(), user["id"]),
                )
                conn.execute(
                    """
                    INSERT INTO password_reset_tokens
                        (user_id, token_hash, expires_at, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user["id"], digest, expires, utcnow()),
                )
            reset_url = f"{base_url}{url_for('reset_password', token=token)}"
            _enqueue_email(
                str(user["email"]),
                "Reset your Software Release Radar password",
                (
                    f"A password reset was requested for {user['username']}.\n\n"
                    f"Use this link within one hour:\n{reset_url}\n\n"
                    "If you did not request this, ignore this email."
                ),
            )
        else:
            hmac.compare_digest(digest, token_digest(secrets.token_urlsafe(40)))

        _minimum_reset_delay(started)
        flash(
            "If that active account has an email address and SMTP is configured, "
            "a reset link has been sent.",
            "success",
        )
        return redirect(url_for("login"))

    app.view_functions["forgot_password"] = secure_forgot_password

    @app.before_request
    def validated_security_controls():
        settings_response = _validate_settings_submission()
        if settings_response is not None:
            return settings_response

        if (
            request.method != "POST"
            or request.endpoint not in {"assistant_run", "assistant"}
            or g.user is None
            or not _csrf_is_valid()
        ):
            return None

        action = request.form.get("action", "chat")
        if request.endpoint == "assistant_run" and action not in {"analyse", "chat"}:
            return None
        if request.endpoint == "assistant" and action == "clear":
            return None
        action = "analyse" if action == "analyse" else "chat"

        tracker_id = request.form.get("tracker_id", type=int)
        if not tracker_id:
            return None
        with connect() as conn:
            tracker = conn.execute(
                "SELECT * FROM trackers WHERE id = ?",
                (tracker_id,),
            ).fetchone()
        if tracker is None:
            return None

        if action == "chat":
            question = request.form.get("message", "").strip()
            if not question:
                return None
            max_chars = _int_env(
                "AI_QUESTION_MAX_CHARS",
                _AI_DEFAULT_QUESTION_CHARS,
                minimum=250,
                maximum=20_000,
            )
            if len(question) > max_chars:
                return _ai_error(
                    f"Assistant question must not exceed {max_chars} characters.",
                    400,
                )
        else:
            cached = _recent_analysis(int(g.user["id"]), tracker)
            if cached is not None:
                return _cached_analysis_response(cached)

        try:
            lease_id = _acquire_ai_lease(
                app,
                int(g.user["id"]),
                request.remote_addr or "unknown",
            )
        except AIUsageLimitError as exc:
            return _ai_error(str(exc), 429)

        g.ai_security_lease_id = lease_id
        g.ai_security_user_id = int(g.user["id"])
        g.ai_security_tracker_id = int(tracker_id)
        return None

    def release_request_resources() -> None:
        lease_id = getattr(g, "ai_security_lease_id", None)
        if not lease_id:
            return
        try:
            _release_ai_lease(str(lease_id))
        finally:
            g.ai_security_lease_id = None

    @app.after_request
    def release_ai_security_lease(response):
        lease_id = getattr(g, "ai_security_lease_id", None)
        if lease_id and response.status_code < 400:
            try:
                _prune_ai_history(
                    int(g.ai_security_user_id),
                    int(g.ai_security_tracker_id),
                )
            except Exception:
                app.logger.warning("Assistant history pruning failed.", exc_info=True)
        release_request_resources()
        return response

    @app.teardown_request
    def release_ai_security_lease_on_error(_exc):
        release_request_resources()
