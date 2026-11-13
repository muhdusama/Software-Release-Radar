from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

DEFAULT_ITERATIONS = 600_000


def hash_password(password: str, salt: bytes | None = None, iterations: int = DEFAULT_ITERATIONS) -> str:
    if not isinstance(password, str) or len(password) < 10:
        raise ValueError("Password must contain at least 10 characters.")
    salt = salt or secrets.token_bytes(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return ":".join(
        [
            "pbkdf2_sha256",
            str(iterations),
            base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_iterations, raw_salt, raw_digest = encoded.split(":", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(raw_iterations)
        salt = base64.urlsafe_b64decode(raw_salt + "=" * (-len(raw_salt) % 4))
        expected = base64.urlsafe_b64decode(raw_digest + "=" * (-len(raw_digest) % 4))
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_valid_password_hash(encoded: str) -> bool:
    """True when ``encoded`` is a well-formed pbkdf2_sha256 hash that verify_password can use."""
    try:
        algorithm, raw_iterations, raw_salt, raw_digest = encoded.split(":", 3)
        if algorithm != "pbkdf2_sha256" or int(raw_iterations) < 1:
            return False
        salt = base64.urlsafe_b64decode(raw_salt + "=" * (-len(raw_salt) % 4))
        digest = base64.urlsafe_b64decode(raw_digest + "=" * (-len(raw_digest) % 4))
    except (ValueError, TypeError):
        return False
    return bool(salt) and len(digest) == 32


def setup_token(secret_key: str) -> str:
    """Deterministic first-run setup token derived from SECRET_KEY.

    Derivation (rather than storage) gives every gunicorn worker and every restart the same
    value to log, and the token stops mattering once any user exists.
    """
    return hmac.new(secret_key.encode("utf-8"), b"software-release-radar-first-run-setup",
                    hashlib.sha256).hexdigest()[:32]
