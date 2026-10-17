from __future__ import annotations

import json
import urllib.error
import urllib.request

from .db import get_settings
from .http_client import open_http, validate_http_url
from .secrets_store import decrypt_secret
from .version import APP_VERSION


class AIClientError(RuntimeError):
    pass


_MAX_MESSAGES = 24
_MAX_MESSAGE_CHARS = 40_000
_MAX_PROMPT_CHARS = 80_000
_MAX_OUTPUT_CHARS = 100_000


AI_KEYS = [
    "openai_enabled", "openai_base_url", "openai_api_key_enc", "openai_model",
    "openai_timeout", "openai_max_tokens",
]


def _enabled(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def config() -> dict[str, object]:
    raw = get_settings(AI_KEYS)
    base_url = raw["openai_base_url"].strip().rstrip("/")
    if base_url:
        try:
            base_url = validate_http_url(base_url, label="OpenAI-compatible base URL")
        except ValueError as exc:
            raise AIClientError(str(exc)) from exc
    return {
        "enabled": _enabled(raw["openai_enabled"]),
        "base_url": base_url,
        "api_key": decrypt_secret(raw["openai_api_key_enc"]),
        "model": raw["openai_model"].strip(),
        "timeout": max(10, min(120, int(raw["openai_timeout"] or 120))),
        "max_tokens": max(200, min(4096, int(raw["openai_max_tokens"] or 1800))),
    }


def _check_prompt_size(messages: list[dict[str, str]]) -> None:
    if len(messages) > _MAX_MESSAGES:
        raise AIClientError(f"Assistant requests must not exceed {_MAX_MESSAGES} messages.")
    total = 0
    for message in messages:
        content = str(message.get("content") or "")
        if len(content) > _MAX_MESSAGE_CHARS:
            raise AIClientError(
                f"An Assistant message exceeds the {_MAX_MESSAGE_CHARS}-character limit."
            )
        total += len(content)
    if total > _MAX_PROMPT_CHARS:
        raise AIClientError(f"Assistant prompt exceeds the {_MAX_PROMPT_CHARS}-character limit.")


def chat(messages: list[dict[str, str]], *, temperature: float = 0.2) -> tuple[str, str]:
    _check_prompt_size(messages)
    try:
        cfg = config()
    except RuntimeError as exc:
        raise AIClientError(str(exc)) from exc
    if not cfg["enabled"]:
        raise AIClientError("OpenAI-compatible support is disabled in Settings.")
    if not cfg["base_url"] or not cfg["api_key"] or not cfg["model"]:
        raise AIClientError("OpenAI-compatible base URL, API key, and model are required.")
    endpoint = str(cfg["base_url"]) + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": cfg["max_tokens"],
        "stream": False,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"Software-Release-Radar/{APP_VERSION}",
        },
    )
    try:
        with open_http(request, timeout=int(cfg["timeout"])) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1200]
        raise AIClientError(f"OpenAI-compatible endpoint returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AIClientError(f"Could not reach the OpenAI-compatible endpoint: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AIClientError("OpenAI-compatible endpoint returned an unreadable response.") from exc

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIClientError("OpenAI-compatible response did not contain choices[0].message.content.") from exc
    if isinstance(content, list):
        content = "\n".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
    content = str(content or "").strip()
    if not content:
        raise AIClientError("The configured model returned an empty response.")
    if len(content) > _MAX_OUTPUT_CHARS:
        raise AIClientError(f"Assistant response exceeds the {_MAX_OUTPUT_CHARS}-character limit.")
    return content, str(result.get("model") or cfg["model"])


def test_connection() -> str:
    content, model = chat([
        {"role": "system", "content": "Reply with exactly: Software Release Radar connection OK"},
        {"role": "user", "content": "Connection test"},
    ], temperature=0)
    return f"{model}: {content[:200]}"
