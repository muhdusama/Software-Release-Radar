#!/usr/bin/env python3
from __future__ import annotations

import base64
import getpass
import hashlib
import os
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")


def password_hash(password: str, iterations: int = 600_000) -> str:
    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters.")
    salt = secrets.token_bytes(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return ":".join([
        "pbkdf2_sha256",
        str(iterations),
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
    ])


def main() -> None:
    if ENV_PATH.exists():
        raise SystemExit(".env already exists. Move or remove it before running bootstrap again.")
    if not EXAMPLE_PATH.exists():
        raise SystemExit(".env.example is missing.")

    username = input("Admin username [admin]: ").strip() or "admin"
    if not USERNAME_RE.fullmatch(username):
        raise SystemExit("Username must be 3 to 64 characters using letters, numbers, dots, dashes or underscores.")

    email = input("Admin email [optional]: ").strip()

    password = getpass.getpass("Admin password: ")
    confirm = getpass.getpass("Confirm admin password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")

    try:
        encoded_password = password_hash(password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    secret_key = secrets.token_urlsafe(48)
    encryption_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")

    values = {
        "ADMIN_USERNAME": username,
        "ADMIN_EMAIL": email,
        "ADMIN_PASSWORD_HASH": encoded_password,
        "SECRET_KEY": secret_key,
        "ENCRYPTION_KEY": encryption_key,
    }

    output = []
    for line in EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            output.append(line)
            continue
        key, current = line.split("=", 1)
        output.append(f"{key}={values.get(key, current)}")

    ENV_PATH.write_text("\n".join(output) + "\n", encoding="utf-8")
    ENV_PATH.chmod(0o600)
    (ROOT / "ssh").mkdir(exist_ok=True)
    print()
    print("Created .env with secure application secrets.")
    print("Next: docker compose up -d --build")


if __name__ == "__main__":
    main()
