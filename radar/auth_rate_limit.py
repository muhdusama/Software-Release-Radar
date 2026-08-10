from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from datetime import datetime, timedelta, timezone

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

from .auth import hash_password, verify_password
from .db import connect, transaction, utcnow
from .tracker_utils import parse_utc

LOGIN_USERNAME_THRESHOLD = 8
LOGIN_IP_THRESHOLD = 20
RESET_IDENTITY_THRESHOLD = 3
RESET_IP_THRESHOLD = 10
WINDOW_SECONDS = 15 * 60
BLOCK_SECONDS = 15 * 60


def _ensure_table() -> None:
    with transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_rate_limits (
                key TEXT PRIMARY KEY,
                failures INTEGER NOT NULL DEFAULT 0,
                window_started_at TEXT NOT NULL,
                blocked_until TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )


def _key(secret_key: str, namespace: str, value: str) -> str:
    normalised = (value or "unknown").strip().casefold()
    return hmac.new(
        secret_key.encode("utf-8"),
        f"{namespace}:{normalised}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _remaining_seconds(keys: list[str]) -> int:
    if not keys:
        return 0
    placeholders = ",".join("?" for _ in keys)
    now = datetime.now(timezone.utc)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT blocked_until FROM auth_rate_limits WHERE key IN ({placeholders})",
            keys,
        ).fetchall()
    remaining = 0
    for row in rows:
        blocked_until = parse_utc(row["blocked_until"])
        if blocked_until and blocked_until > now:
            remaining = max(remaining, math.ceil((blocked_until - now).total_seconds()))
    return remaining


def _record_failure(key: str, threshold: int) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    window_cutoff = now - timedelta(seconds=WINDOW_SECONDS)
    with transaction() as conn:
        row = conn.execute(
            "SELECT failures, window_started_at, blocked_until FROM auth_rate_limits WHERE key = ?",
            (key,),
        ).fetchone()

        window_started = parse_utc(row["window_started_at"]) if row else None
        blocked_until = parse_utc(row["blocked_until"]) if row else None

        if not window_started or window_started < window_cutoff:
            failures = 1
            window_started = now
            blocked_until = None
        else:
            failures = int(row["failures"] or 0) + 1

        if failures >= threshold:
            blocked_until = max(
                blocked_until or now,
                now + timedelta(seconds=BLOCK_SECONDS),
            )

        conn.execute(
            """
            INSERT INTO auth_rate_limits
                (key, failures, window_started_at, blocked_until, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                failures = excluded.failures,
                window_started_at = excluded.window_started_at,
                blocked_until = excluded.blocked_until,
                updated_at = excluded.updated_at
            """,
            (
                key,
                failures,
                window_started.isoformat(),
                blocked_until.isoformat() if blocked_until else None,
                now.isoformat(),
            ),
        )
        conn.execute(
            "DELETE FROM auth_rate_limits WHERE updated_at < ?",
            ((now - timedelta(days=2)).isoformat(),),
        )


def _clear_key(key: str) -> None:
    with transaction() as conn:
        conn.execute("DELETE FROM auth_rate_limits WHERE key = ?", (key,))


def install_auth_rate_limits(app: Flask) -> None:
    """Install SQLite-backed login and reset-request throttling on an app."""
    _ensure_table()
    secret_key = str(app.secret_key or "")
    if not secret_key:
        raise RuntimeError("Application secret key must be configured before auth rate limiting.")

    # Existing and unknown usernames should have similar password-work cost.
    dummy_password_hash = hash_password(secrets.token_urlsafe(32))

    @app.before_request
    def auth_rate_limit_before_request():
        if request.method != "POST":
            return None

        remote = request.remote_addr or "unknown"

        if request.endpoint == "login":
            username = request.form.get("username", "").strip()
            username_key = _key(secret_key, "login-username", username)
            ip_key = _key(secret_key, "login-ip", remote)
            g.auth_rate_login_keys = (username_key, ip_key)
            remaining = _remaining_seconds([username_key, ip_key])
            if remaining:
                g.auth_rate_blocked = True
                minutes = max(1, math.ceil(remaining / 60))
                flash(f"Too many sign-in attempts. Try again in about {minutes} minute{'s' if minutes != 1 else ''}.", "error")
                return render_template("login.html"), 429

            # Equalise the most obvious existing-user versus unknown-user timing gap.
            with connect() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE LIMIT 1",
                    (username,),
                ).fetchone()
            if not exists:
                verify_password(request.form.get("password", ""), dummy_password_hash)
            return None

        if request.endpoint == "forgot_password":
            identity = request.form.get("identity", "").strip()
            identity_key = _key(secret_key, "reset-identity", identity)
            ip_key = _key(secret_key, "reset-ip", remote)
            remaining = _remaining_seconds([identity_key, ip_key])
            if remaining:
                flash("If that active account has an email address and SMTP is configured, a reset link has been sent.", "success")
                return redirect(url_for("login"))
            _record_failure(identity_key, RESET_IDENTITY_THRESHOLD)
            _record_failure(ip_key, RESET_IP_THRESHOLD)

        return None

    @app.after_request
    def auth_rate_limit_after_request(response):
        if (
            request.method == "POST"
            and request.endpoint == "login"
            and not getattr(g, "auth_rate_blocked", False)
            and response.status_code != 400
        ):
            username_key, ip_key = getattr(g, "auth_rate_login_keys", (None, None))
            if username_key and ip_key:
                if session.get("user_id"):
                    # A valid login clears that account's failure counter. The IP
                    # counter is allowed to decay naturally so one known account
                    # cannot reset brute-force attempts against other accounts.
                    _clear_key(username_key)
                else:
                    _record_failure(username_key, LOGIN_USERNAME_THRESHOLD)
                    _record_failure(ip_key, LOGIN_IP_THRESHOLD)
        return response
