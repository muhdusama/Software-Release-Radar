"""Administrator-configured, system-level release alert channels.

Webhook, ntfy and Gotify are delivered once per release event rather than once
per user. Release notes are never sent; every outgoing value is plain text and
truncated.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .db import get_settings
from .http_client import open_http
from .secrets_store import decrypt_secret, encrypt_secret
from .security_policy import _is_loopback_host, insecure_integrations_allowed
from .version import APP_VERSION

SYSTEM_CHANNELS = ("webhook", "ntfy", "gotify")
SYSTEM_CHANNEL_LABELS = {"webhook": "Webhook", "ntfy": "ntfy", "gotify": "Gotify"}
SYSTEM_CHANNEL_KEYS = [
    "webhook_enabled", "webhook_url", "webhook_token_enc", "webhook_secret_enc",
    "ntfy_enabled", "ntfy_server_url", "ntfy_topic", "ntfy_token_enc",
    "gotify_enabled", "gotify_url", "gotify_token_enc",
]
DEFAULT_NTFY_SERVER = "https://ntfy.sh"
TIMEOUT_SECONDS = 10
_TOPIC = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SystemChannelError(RuntimeError):
    pass


def _on(value: str | None) -> bool:
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def validate_channel_url(value: str, label: str) -> str:
    """Return a clean URL. HTTPS is required unless loopback or explicitly allowed."""
    url = str(value or "").strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{label} must be a complete http:// or https:// URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} must not include embedded credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{label} must not include a query or fragment.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} contains an invalid port.") from exc
    if parsed.scheme == "http" and not (
        _is_loopback_host(parsed.hostname) or insecure_integrations_allowed()
    ):
        raise ValueError(
            f"{label} must use HTTPS. Set ALLOW_INSECURE_INTEGRATIONS=true only for "
            "an explicitly accepted trusted-network exception."
        )
    return url.rstrip("/")


def settings_from_form(form, existing: dict[str, str]) -> dict[str, str]:
    """Validate the Settings form and return values to store. Blank secrets keep the saved value."""
    values: dict[str, str] = {}
    for channel in SYSTEM_CHANNELS:
        values[f"{channel}_enabled"] = "1" if form.get(f"{channel}_enabled") else "0"
    enabled = {c: values[f"{c}_enabled"] == "1" for c in SYSTEM_CHANNELS}

    url = form.get("webhook_url", "").strip()
    values["webhook_url"] = validate_channel_url(url, "Webhook URL") if url else ""
    server = form.get("ntfy_server_url", "").strip() or DEFAULT_NTFY_SERVER
    values["ntfy_server_url"] = validate_channel_url(server, "ntfy server URL")
    topic = form.get("ntfy_topic", "").strip()
    if topic and not _TOPIC.match(topic):
        raise ValueError("ntfy topic may contain only letters, digits, hyphens and underscores (64 characters at most).")
    values["ntfy_topic"] = topic
    gotify = form.get("gotify_url", "").strip()
    values["gotify_url"] = validate_channel_url(gotify, "Gotify URL") if gotify else ""

    for key, field in (
        ("webhook_token_enc", "webhook_token"), ("webhook_secret_enc", "webhook_secret"),
        ("ntfy_token_enc", "ntfy_token"), ("gotify_token_enc", "gotify_token"),
    ):
        supplied = form.get(field, "").strip()
        if supplied:
            values[key] = encrypt_secret(supplied)
        elif form.get(f"clear_{field}"):
            values[key] = ""

    merged = {**existing, **values}
    if enabled["webhook"] and not merged["webhook_url"]:
        raise ValueError("A webhook URL is required to enable the webhook channel.")
    if enabled["ntfy"] and not merged["ntfy_topic"]:
        raise ValueError("An ntfy topic is required to enable the ntfy channel.")
    if enabled["gotify"] and not (merged["gotify_url"] and merged["gotify_token_enc"]):
        raise ValueError("A Gotify URL and application token are required to enable Gotify.")
    return values


def channel_configured(raw: dict[str, str], channel: str) -> bool:
    if channel == "webhook":
        return bool(raw["webhook_url"])
    if channel == "ntfy":
        return bool(raw["ntfy_topic"])
    return bool(raw["gotify_url"] and raw["gotify_token_enc"])


def enabled_system_channels() -> list[str]:
    raw = get_settings(SYSTEM_CHANNEL_KEYS)
    return [c for c in SYSTEM_CHANNELS if _on(raw[f"{c}_enabled"]) and channel_configured(raw, c)]


def _text(value, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def webhook_payload(event) -> dict[str, str | None]:
    release = _text(event["release_name"] or event["version"], 200)
    installed = event["detected_installed_version"] or event["installed_version"]
    return {
        "event": "release.detected",
        "software": _text(event["name"], 200),
        "repository": _text(event["repository"], 200),
        "machine": _text(event["machine_name"] or event["install_host"], 200) or None,
        "installed_version": _text(installed, 100) or None,
        "new_version": release,
        "release_url": _text(event["release_url"], 512) or None,
        "detected_at": _text(event["detected_at"], 64),
        "app_version": APP_VERSION,
    }


def smoke_event() -> dict[str, str | None]:
    return {
        "name": "Software Release Radar test", "repository": "example/test",
        "machine_name": None, "install_host": None,
        "detected_installed_version": None, "installed_version": None,
        "release_name": "test", "version": "test", "release_url": None,
        "detected_at": "", "tags": "",
    }


def _post(url: str, body: bytes, headers: dict[str, str], label: str) -> None:
    validate_channel_url(url, f"{label} URL")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"User-Agent": f"Software-Release-Radar/{APP_VERSION}", **headers},
    )
    try:
        with open_http(request, timeout=TIMEOUT_SECONDS) as response:
            response.read(4096)
    except urllib.error.HTTPError as exc:
        raise SystemChannelError(f"{label} returned HTTP {exc.code}.") from exc
    except (OSError, http.client.HTTPException) as exc:
        reason = getattr(exc, "reason", exc)
        raise SystemChannelError(f"{label} delivery failed: {_text(reason, 200)}") from exc


def _send_webhook(raw: dict[str, str], event, title: str, message: str) -> None:
    body = json.dumps(webhook_payload(event), sort_keys=True).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = decrypt_secret(raw["webhook_token_enc"])
    if token:
        headers["Authorization"] = f"Bearer {token}"
    secret = decrypt_secret(raw["webhook_secret_enc"])
    if secret:
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-Radar-Signature"] = f"sha256={digest}"
    _post(raw["webhook_url"], body, headers, "Webhook")


def _send_ntfy(raw: dict[str, str], event, title: str, message: str) -> None:
    payload = {
        "topic": raw["ntfy_topic"], "title": _text(title, 250),
        "message": _text(message, 1024), "tags": ["package"],
    }
    if event["release_url"]:
        payload["click"] = _text(event["release_url"], 512)
    headers = {"Content-Type": "application/json"}
    token = decrypt_secret(raw["ntfy_token_enc"])
    if token:
        headers["Authorization"] = f"Bearer {token}"
    _post(raw["ntfy_server_url"] or DEFAULT_NTFY_SERVER, json.dumps(payload).encode("utf-8"), headers, "ntfy")


def _send_gotify(raw: dict[str, str], event, title: str, message: str) -> None:
    payload: dict[str, object] = {
        "title": _text(title, 250), "message": _text(message, 1024), "priority": 5,
    }
    if event["release_url"]:
        payload["extras"] = {
            "client::notification": {"click": {"url": _text(event["release_url"], 512)}}
        }
    token = decrypt_secret(raw["gotify_token_enc"])
    _post(
        raw["gotify_url"].rstrip("/") + "/message", json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json", "X-Gotify-Key": token}, "Gotify",
    )


_SENDERS = {"webhook": _send_webhook, "ntfy": _send_ntfy, "gotify": _send_gotify}


def send_system_channel(channel: str, event, title: str, message: str) -> None:
    """Send one release alert through a system channel or raise SystemChannelError."""
    raw = get_settings(SYSTEM_CHANNEL_KEYS)
    if not channel_configured(raw, channel):
        raise SystemChannelError(f"{SYSTEM_CHANNEL_LABELS[channel]} is not configured.")
    _SENDERS[channel](raw, event, title, message)
