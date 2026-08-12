from __future__ import annotations

import functools
import smtplib
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from .security_policy import (
    _is_loopback_host,
    insecure_integrations_allowed,
)

_HTTP_CREDENTIAL_HEADERS = {"authorization", "proxy-authorization", "x-api-key"}
_AI_RESPONSE_LIMIT = 2 * 1024 * 1024
_INTEGRATION_RESPONSE_LIMIT = 10 * 1024 * 1024
_AI_MAX_MESSAGES = 24
_AI_MAX_MESSAGE_CHARS = 40_000
_AI_MAX_PROMPT_CHARS = 80_000
_AI_MAX_OUTPUT_CHARS = 100_000
_INSTALLED = False


class _BoundedResponse:
    def __init__(self, response: Any, limit: int):
        self._response = response
        self._limit = int(limit)
        self._read = 0
        content_length = None
        try:
            raw = response.headers.get("Content-Length")
            content_length = int(raw) if raw else None
        except (AttributeError, TypeError, ValueError):
            content_length = None
        if content_length is not None and content_length > self._limit:
            response.close()
            raise urllib.error.URLError(
                f"Integration response exceeds the {self._limit}-byte safety limit."
            )

    def __enter__(self):
        self._response.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._response.__exit__(exc_type, exc_value, traceback)

    def __getattr__(self, name: str):
        return getattr(self._response, name)

    def read(self, amount: int | None = -1) -> bytes:
        remaining = self._limit - self._read
        if remaining < 0:
            raise urllib.error.URLError(
                f"Integration response exceeds the {self._limit}-byte safety limit."
            )
        requested = remaining + 1 if amount in (None, -1) else min(int(amount), remaining + 1)
        data = self._response.read(requested)
        self._read += len(data)
        if self._read > self._limit:
            raise urllib.error.URLError(
                f"Integration response exceeds the {self._limit}-byte safety limit."
            )
        return data


def _request_details(target: Any) -> tuple[str, set[str]]:
    if isinstance(target, urllib.request.Request):
        url = target.full_url
        headers = {str(key).lower() for key, _ in target.header_items()}
    else:
        url = str(target)
        headers = set()
    return url, headers


def _install_http_guard() -> None:
    if getattr(urllib.request.urlopen, "_radar_security_guard", False):
        return
    original_urlopen = urllib.request.urlopen
    original_redirect_request = urllib.request.HTTPRedirectHandler.redirect_request

    @functools.wraps(original_redirect_request)
    def guarded_redirect_request(self, req, fp, code, msg, headers, newurl):
        original_url, request_headers = _request_details(req)
        if request_headers & _HTTP_CREDENTIAL_HEADERS:
            original = urlsplit(original_url)
            target = urlsplit(newurl)
            original_origin = (
                original.scheme,
                original.hostname,
                original.port or (443 if original.scheme == "https" else 80),
            )
            target_origin = (
                target.scheme,
                target.hostname,
                target.port or (443 if target.scheme == "https" else 80),
            )
            if original_origin != target_origin:
                raise urllib.error.HTTPError(
                    original_url,
                    code,
                    "Credential-bearing integration redirects must remain on the same origin.",
                    headers,
                    fp,
                )
            if (
                target.scheme == "http"
                and not _is_loopback_host(target.hostname)
                and not insecure_integrations_allowed()
            ):
                raise urllib.error.HTTPError(
                    original_url,
                    code,
                    "Credential-bearing integration redirects must not downgrade to HTTP.",
                    headers,
                    fp,
                )
        return original_redirect_request(self, req, fp, code, msg, headers, newurl)

    @functools.wraps(original_urlopen)
    def guarded_urlopen(target, *args, **kwargs):
        url, headers = _request_details(target)
        parsed = urlsplit(url)
        has_credentials = bool(headers & _HTTP_CREDENTIAL_HEADERS)
        if (
            parsed.scheme == "http"
            and has_credentials
            and not _is_loopback_host(parsed.hostname)
            and not insecure_integrations_allowed()
        ):
            raise urllib.error.URLError(
                "Credential-bearing integration requests require HTTPS. "
                "Set ALLOW_INSECURE_INTEGRATIONS=true only for an explicitly "
                "accepted trusted-network exception."
            )
        response = original_urlopen(target, *args, **kwargs)
        if has_credentials:
            limit = (
                _AI_RESPONSE_LIMIT
                if "authorization" in headers
                else _INTEGRATION_RESPONSE_LIMIT
            )
            return _BoundedResponse(response, limit)
        return response

    guarded_urlopen._radar_security_guard = True
    guarded_urlopen._radar_original = original_urlopen
    urllib.request.HTTPRedirectHandler.redirect_request = guarded_redirect_request
    urllib.request.urlopen = guarded_urlopen


def _install_smtp_guard() -> None:
    if getattr(smtplib.SMTP, "_radar_security_guard", False):
        return

    original_smtp_init = smtplib.SMTP.__init__
    original_ssl_init = smtplib.SMTP_SSL.__init__
    original_starttls = smtplib.SMTP.starttls
    original_send_message = smtplib.SMTP.send_message
    original_sendmail = smtplib.SMTP.sendmail

    @functools.wraps(original_smtp_init)
    def smtp_init(self, *args, **kwargs):
        original_smtp_init(self, *args, **kwargs)
        self._radar_tls_active = False

    @functools.wraps(original_ssl_init)
    def smtp_ssl_init(self, *args, **kwargs):
        original_ssl_init(self, *args, **kwargs)
        self._radar_tls_active = True

    @functools.wraps(original_starttls)
    def smtp_starttls(self, *args, **kwargs):
        result = original_starttls(self, *args, **kwargs)
        self._radar_tls_active = True
        return result

    def require_secure_smtp(self) -> None:
        host = str(getattr(self, "_host", "") or "")
        if getattr(self, "_radar_tls_active", False):
            return
        if _is_loopback_host(host) or insecure_integrations_allowed():
            return
        raise smtplib.SMTPException(
            "SMTP delivery requires STARTTLS or implicit TLS. "
            "Set ALLOW_INSECURE_INTEGRATIONS=true only for an explicitly "
            "accepted trusted-network exception."
        )

    @functools.wraps(original_send_message)
    def smtp_send_message(self, *args, **kwargs):
        require_secure_smtp(self)
        return original_send_message(self, *args, **kwargs)

    @functools.wraps(original_sendmail)
    def smtp_sendmail(self, *args, **kwargs):
        require_secure_smtp(self)
        return original_sendmail(self, *args, **kwargs)

    smtplib.SMTP.__init__ = smtp_init
    smtplib.SMTP_SSL.__init__ = smtp_ssl_init
    smtplib.SMTP.starttls = smtp_starttls
    smtplib.SMTP.send_message = smtp_send_message
    smtplib.SMTP.sendmail = smtp_sendmail
    smtplib.SMTP._radar_security_guard = True


def _install_ai_guard() -> None:
    from . import ai_client

    if getattr(ai_client.chat, "_radar_security_guard", False):
        return

    original_config = ai_client.config
    original_chat = ai_client.chat

    @functools.wraps(original_config)
    def secure_config() -> dict[str, object]:
        cfg = dict(original_config())
        cfg["timeout"] = max(10, min(120, int(cfg.get("timeout") or 120)))
        cfg["max_tokens"] = max(200, min(4096, int(cfg.get("max_tokens") or 1800)))
        return cfg

    @functools.wraps(original_chat)
    def secure_chat(messages: list[dict[str, str]], *, temperature: float = 0.2):
        if len(messages) > _AI_MAX_MESSAGES:
            raise ai_client.AIClientError(
                f"Assistant requests must not exceed {_AI_MAX_MESSAGES} messages."
            )
        total = 0
        for message in messages:
            content = str(message.get("content") or "")
            if len(content) > _AI_MAX_MESSAGE_CHARS:
                raise ai_client.AIClientError(
                    f"An Assistant message exceeds the {_AI_MAX_MESSAGE_CHARS}-character limit."
                )
            total += len(content)
        if total > _AI_MAX_PROMPT_CHARS:
            raise ai_client.AIClientError(
                f"Assistant prompt exceeds the {_AI_MAX_PROMPT_CHARS}-character limit."
            )
        answer, model = original_chat(messages, temperature=temperature)
        if len(answer) > _AI_MAX_OUTPUT_CHARS:
            raise ai_client.AIClientError(
                f"Assistant response exceeds the {_AI_MAX_OUTPUT_CHARS}-character limit."
            )
        return answer, model

    secure_chat._radar_security_guard = True
    ai_client.config = secure_config
    ai_client.chat = secure_chat


def _install_probe_guard() -> None:
    from . import probes
    from .safe_regex import SafeRegexError, search_version

    if getattr(probes._probe_http_regex, "_radar_security_guard", False):
        return

    def secure_probe_http_regex(tracker):
        path = str(tracker["version_probe_path"] or tracker["health_path"] or "/")
        pattern = str(tracker["version_regex"] or "").strip()
        body, _, latency = probes._http_get(probes._base_url(tracker, path))
        try:
            value = search_version(pattern, body.decode("utf-8", "replace"))
        except SafeRegexError as exc:
            raise ValueError(str(exc)) from exc
        if value is None:
            raise ValueError("Version regular expression did not match the response.")
        return value.strip(), latency, f"HTTP regex {path}"

    secure_probe_http_regex._radar_security_guard = True
    probes._probe_http_regex = secure_probe_http_regex


def install_runtime_guards() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_http_guard()
    _install_smtp_guard()
    _install_ai_guard()
    _install_probe_guard()
    _INSTALLED = True
