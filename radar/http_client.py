from __future__ import annotations

import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .security_policy import _is_loopback_host, insecure_integrations_allowed


_ALLOWED_SCHEMES = {"http", "https"}
_CREDENTIAL_HEADERS = {"authorization", "proxy-authorization", "x-api-key"}
_AUTHORIZATION_RESPONSE_LIMIT = 2 * 1024 * 1024
_INTEGRATION_RESPONSE_LIMIT = 10 * 1024 * 1024


def validate_http_url(value: str, *, label: str = "URL") -> str:
    """Return a normalised HTTP(S) URL or reject unsupported schemes."""
    url = str(value or "").strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES or not parsed.hostname:
        raise ValueError(f"{label} must be a complete http:// or https:// URL.")
    if parsed.username or parsed.password:
        raise ValueError(f"{label} must not contain embedded credentials.")
    return url


class BoundedResponse:
    """Wrap a response so reading more than ``limit`` bytes fails."""

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


def _origin(parsed: urllib.parse.SplitResult) -> tuple[str, str | None, int]:
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


def _is_cleartext_remote(parsed: urllib.parse.SplitResult) -> bool:
    return (
        parsed.scheme == "http"
        and not _is_loopback_host(parsed.hostname)
        and not insecure_integrations_allowed()
    )


def _credential_headers(request: urllib.request.Request) -> set[str]:
    return {str(key).lower() for key, _ in request.header_items()} & _CREDENTIAL_HEADERS


class _CredentialRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep credential-bearing redirects on the same origin and off cleartext HTTP."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _credential_headers(req):
            original = urllib.parse.urlsplit(req.full_url)
            target = urllib.parse.urlsplit(newurl)
            if _origin(original) != _origin(target):
                raise urllib.error.HTTPError(
                    req.full_url, code,
                    "Credential-bearing integration redirects must remain on the same origin.",
                    headers, fp,
                )
            if _is_cleartext_remote(target):
                raise urllib.error.HTTPError(
                    req.full_url, code,
                    "Credential-bearing integration redirects must not downgrade to HTTP.",
                    headers, fp,
                )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_http(
    request: urllib.request.Request | str,
    *,
    timeout: float,
    context: ssl.SSLContext | None = None,
) -> Any:
    """Open an HTTP(S) request with the integration transport rules applied.

    Callers may intentionally reach private network addresses because local service
    probing and self-hosted integrations are product features. This helper:

    - limits urllib to HTTP(S) so file:, ftp: and custom URL handlers cannot be selected;
    - refuses to send credential headers over cleartext HTTP to a non-loopback host
      unless ALLOW_INSECURE_INTEGRATIONS=true;
    - keeps credential-bearing redirects on the original origin; and
    - bounds the size of credential-bearing responses.
    """
    if not isinstance(request, urllib.request.Request):
        request = urllib.request.Request(str(request))
    validate_http_url(request.full_url)
    credentials = _credential_headers(request)
    if credentials and _is_cleartext_remote(urllib.parse.urlsplit(request.full_url)):
        raise urllib.error.URLError(
            "Credential-bearing integration requests require HTTPS. "
            "Set ALLOW_INSECURE_INTEGRATIONS=true only for an explicitly "
            "accepted trusted-network exception."
        )
    handlers: list[urllib.request.BaseHandler] = [_CredentialRedirectHandler()]
    if context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    # The scheme is validated above, so only HTTP(S) handlers can be selected.
    response = urllib.request.build_opener(*handlers).open(request, timeout=timeout)  # nosec B310
    if credentials:
        limit = (
            _AUTHORIZATION_RESPONSE_LIMIT
            if "authorization" in credentials
            else _INTEGRATION_RESPONSE_LIMIT
        )
        return BoundedResponse(response, limit)
    return response
