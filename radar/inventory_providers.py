from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from .db import get_settings
from .secrets_store import decrypt_secret
from .version import APP_VERSION


class InventoryProviderError(RuntimeError):
    """A provider request failed without exposing credentials."""


class EnvironmentUnavailable(InventoryProviderError):
    """An environment is known but its Docker connection is unavailable."""


def validate_origin_url(value: str, label: str) -> str:
    """Return a normalised HTTP(S) origin or reject URL components we do not use."""
    value = (value or "").strip()
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise ValueError(f"{label} must be a complete HTTP or HTTPS origin.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} must not include embedded credentials.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError(f"{label} must be an origin without a path, query or fragment.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} contains an invalid port.") from exc
    return value.rstrip("/")


@dataclass(frozen=True)
class InventoryEnvironment:
    source_id: str
    name: str
    url: str = ""
    host: str | None = None
    kind: str = "docker"
    raw: dict[str, Any] | None = None


class InventoryProvider(ABC):
    name: str

    @abstractmethod
    def list_environments(self) -> list[InventoryEnvironment]:
        raise NotImplementedError

    @abstractmethod
    def list_containers(self, environment: InventoryEnvironment) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    def image_labels(self, environment: InventoryEnvironment, image_id: str) -> dict[str, Any]:
        return {}


class DockhandProvider(InventoryProvider):
    name = "dockhand"

    def __init__(self, request: Callable[..., Any] | None = None):
        self._request_override = request

    @staticmethod
    def _settings() -> dict[str, str]:
        return get_settings([
            "dockhand_base_url", "dockhand_api_token_enc",
            "dockhand_verify_tls", "dockhand_timeout",
        ])

    def _request(self, path: str, *, method: str = "GET") -> Any:
        if self._request_override:
            return self._request_override(path, method=method)
        settings = self._settings()
        raw_base_url = (settings.get("dockhand_base_url") or "").strip()
        token = decrypt_secret(settings.get("dockhand_api_token_enc", ""))
        if not raw_base_url:
            raise InventoryProviderError("Dockhand base URL is not configured.")
        try:
            base_url = validate_origin_url(raw_base_url, "Dockhand base URL")
        except ValueError as exc:
            raise InventoryProviderError(str(exc)) from exc
        if not token:
            raise InventoryProviderError("Dockhand API token is not configured.")
        if not path.startswith("/"):
            path = "/" + path
        request = urllib.request.Request(
            base_url + path,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": f"Software-Release-Radar/{APP_VERSION}",
            },
        )
        verify_tls = settings.get("dockhand_verify_tls", "1") == "1"
        context = None if verify_tls else ssl._create_unverified_context()  # noqa: SLF001
        try:
            with urllib.request.urlopen(
                request,
                timeout=int(settings.get("dockhand_timeout") or 20),
                context=context,
            ) as response:
                raw = response.read(10_000_000)
        except urllib.error.HTTPError as exc:
            # Never include a response body because upstream/proxy errors can echo headers.
            raise InventoryProviderError(
                f"Dockhand API returned HTTP {exc.code}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise InventoryProviderError(f"Unable to reach Dockhand: {exc.reason}") from exc
        try:
            return json.loads(raw.decode("utf-8")) if raw else None
        except json.JSONDecodeError as exc:
            raise InventoryProviderError("Dockhand returned an invalid JSON response.") from exc

    @staticmethod
    def _environment(item: dict[str, Any]) -> InventoryEnvironment:
        source_id = str(item.get("id") or "").strip()
        if not source_id:
            raise InventoryProviderError("Dockhand returned an environment without an ID.")
        name = str(item.get("name") or f"Environment {source_id}").strip()
        host = str(item.get("publicIp") or item.get("host") or "").strip() or None
        protocol = str(item.get("protocol") or "").strip()
        port = item.get("port")
        url = ""
        if host:
            url = f"{protocol or 'tcp'}://{host}{f':{port}' if port else ''}"
        return InventoryEnvironment(
            source_id=source_id,
            name=name,
            url=url,
            host=host,
            kind=str(item.get("connectionType") or "docker"),
            raw=item,
        )

    def list_environments(self) -> list[InventoryEnvironment]:
        payload = self._request("/api/environments")
        if not isinstance(payload, list):
            raise InventoryProviderError("Dockhand environment listing returned an unexpected response.")
        result: list[InventoryEnvironment] = []
        for item in payload:
            if not isinstance(item, dict):
                raise InventoryProviderError("Dockhand environment listing contained a malformed item.")
            result.append(self._environment(item))
        return result

    def _assert_online(self, environment: InventoryEnvironment) -> dict[str, Any]:
        payload = self._request(
            f"/api/environments/{urllib.parse.quote(environment.source_id, safe='')}/test",
            method="POST",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("success"), bool):
            raise InventoryProviderError(
                f"{environment.name}: Dockhand connection test returned an unexpected response."
            )
        if not payload["success"]:
            # Deliberately avoid propagating Dockhand's free-form error field.
            raise EnvironmentUnavailable(
                f"{environment.name}: Docker environment is unavailable."
            )
        return payload

    @staticmethod
    def normalise_container(item: dict[str, Any]) -> dict[str, Any]:
        container_id = str(item.get("id") or item.get("Id") or "").strip()
        if not container_id:
            raise InventoryProviderError("Dockhand returned a container without an ID.")
        labels = item["labels"] if "labels" in item else item.get("Labels", {})
        ports = item["ports"] if "ports" in item else item.get("Ports", [])
        if not isinstance(labels, dict) or not isinstance(ports, list):
            raise InventoryProviderError(
                f"Dockhand returned malformed labels or ports for container {container_id}."
            )
        clean_ports = []
        for port in ports:
            if not isinstance(port, dict):
                raise InventoryProviderError(
                    f"Dockhand returned a malformed port for container {container_id}."
                )
            clean_ports.append({
                "PrivatePort": port.get("PrivatePort", port.get("private")),
                "PublicPort": port.get("PublicPort", port.get("public")),
                "Type": port.get("Type", port.get("type", "tcp")),
                "IP": port.get("IP", port.get("ip", "")),
            })
        health = str(item.get("health") or "").strip().lower()
        status = str(item.get("status") or item.get("Status") or "")
        if health and f"({health})" not in status.lower():
            status = f"{status} ({health})".strip()
        return {
            "Id": container_id,
            "Names": ["/" + str(item.get("name") or item.get("Name") or container_id).lstrip("/")],
            "Image": str(item.get("image") or item.get("Image") or ""),
            "ImageID": str(item.get("imageId") or item.get("imageID") or item.get("ImageID") or ""),
            "State": str(item.get("state") or item.get("State") or "unknown"),
            "Status": status,
            "Labels": {str(key): str(value) for key, value in labels.items()},
            "Ports": clean_ports,
        }

    def list_containers(self, environment: InventoryEnvironment) -> list[dict[str, Any]]:
        # Dockhand's list route returns [] for both a genuine empty host and a failed
        # Docker connection. The explicit test route is therefore the fail-safe gate.
        self._assert_online(environment)
        source_id = urllib.parse.quote(environment.source_id, safe="")
        payload = self._request(f"/api/containers?env={source_id}&all=true")
        if not isinstance(payload, list):
            raise InventoryProviderError(
                f"{environment.name}: Dockhand container listing returned an unexpected response."
            )
        result = []
        for item in payload:
            if not isinstance(item, dict):
                raise InventoryProviderError(
                    f"{environment.name}: Dockhand container listing contained a malformed item."
                )
            result.append(self.normalise_container(item))
        return result

    def test_connection(self) -> dict[str, Any]:
        started = time.monotonic()
        environments = self.list_environments()
        online = 0
        for environment in environments:
            try:
                self._assert_online(environment)
            except EnvironmentUnavailable:
                continue
            online += 1
        if environments and online == 0:
            raise InventoryProviderError(
                "Dockhand is reachable, but all configured Docker environments are offline."
            )
        return {
            "ok": True,
            "provider": self.name,
            "latency_ms": max(1, round((time.monotonic() - started) * 1000)),
            "environments": len(environments),
            "online_environments": online,
            "names": [environment.name for environment in environments],
        }
