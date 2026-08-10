from __future__ import annotations

import os
from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not configured.")
    return Fernet(key.encode("ascii"))


def validate_encryption_key() -> None:
    """Fail fast when ENCRYPTION_KEY is missing or invalid."""
    _fernet()


def encrypt_secret(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError("Stored secret could not be decrypted with ENCRYPTION_KEY.") from exc
