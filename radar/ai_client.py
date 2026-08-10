from __future__ import annotations

import json
import urllib.error
import urllib.request

from .db import get_settings
from .secrets_store import decrypt_secret
from .version import APP_VERSION


class AIClientError(RuntimeError):
    pass


AI_KEYS = [
    "openai_enabled", "openai_base_url", "openai_api_key_enc", "openai_model",
    "openai_timeout", "openai_max_tokens",
]


def _enabled(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def config() -> dict[str, object]:
    raw = get_settings(AI_KEYS)
    return {
        "enabled": _enabled(raw["openai_enabled"]),
        "base_url": raw["openai_base_url"].strip().rstrip("/"),
        "api_key": decrypt_secret(raw["openai_api_key_enc"]),
        "model": raw["openai_model"].strip(),
        "timeout": int(raw["openai_timeout"] or 120),
        "max_tokens": int(raw["openai_max_tokens"] or 1800),
    }


def chat(messages: list[dict[str, str]], *, temperature: float = 0.2) -> tuple[str, str]:
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
        with urllib.request.urlopen(request, timeout=int(cfg["timeout"])) as response:
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
    return content, str(result.get("model") or cfg["model"])


def test_connection() -> str:
    content, model = chat([
        {"role": "system", "content": "Reply with exactly: Software Release Radar connection OK"},
        {"role": "user", "content": "Connection test"},
    ], temperature=0)
    return f"{model}: {content[:200]}"
