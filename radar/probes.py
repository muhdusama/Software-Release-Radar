from __future__ import annotations

import ipaddress
import json
import os
import re
import shlex
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import connect, transaction, utcnow
from .version import APP_VERSION
from .portainer import PortainerError, sync_inventory


@dataclass
class ProbeResult:
    tracker_id: int
    status: str
    online: bool
    installed_version: str | None = None
    latency_ms: int | None = None
    error: str | None = None
    source: str | None = None


_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_COMMON_VERSION_PATHS = ("/api/version", "/version", "/api/v1/version", "/health", "/api/info")
_COMMON_JSON_PATHS = ("version", "data.version", "app.version", "build.version", "info.version")


def _validate_host(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) > 253 or not _HOST_RE.fullmatch(value):
        raise ValueError("Machine IP/hostname is invalid.")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        if ".." in value or value.startswith(".") or value.endswith("."):
            raise ValueError("Machine IP/hostname is invalid.")
    return value


def _port(value: Any, default: int | None = None) -> int:
    if value in (None, ""):
        if default is None:
            raise ValueError("Port is required.")
        return default
    port = int(value)
    if port < 1 or port > 65535:
        raise ValueError("Port must be between 1 and 65535.")
    return port


def _connect(host: str, port: int, timeout: float = 4.0) -> int:
    started = time.monotonic()
    with socket.create_connection((host, port), timeout=timeout):
        pass
    return max(1, round((time.monotonic() - started) * 1000))


def _json_path(data: Any, path: str) -> Any:
    current = data
    for segment in [part for part in path.strip().split(".") if part]:
        if isinstance(current, list):
            current = current[int(segment)]
        elif isinstance(current, dict):
            current = current[segment]
        else:
            raise KeyError(segment)
    return current


def _http_get(url: str, timeout: float = 8.0) -> tuple[bytes, dict[str, str], int]:
    started = time.monotonic()
    request = urllib.request.Request(url, headers={"User-Agent": f"Software-Release-Radar/{APP_VERSION}", "Accept": "application/json,text/plain,*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(1_000_000)
        headers = {key.lower(): value for key, value in response.headers.items()}
    latency = max(1, round((time.monotonic() - started) * 1000))
    return body, headers, latency


def _base_url(tracker, path: str | None = None) -> str:
    scheme = str(tracker["install_scheme"] or "http").lower()
    if scheme not in {"http", "https"}:
        scheme = "http"
    host = _validate_host(str(tracker["install_host"] or ""))
    port = _port(tracker["install_port"], 443 if scheme == "https" else 80)
    raw_path = (path or tracker["version_probe_path"] or tracker["health_path"] or "/").strip()
    if not raw_path.startswith("/"):
        raw_path = "/" + raw_path
    return f"{scheme}://{host}:{port}{raw_path}"


def _extract_auto_version(body: bytes, headers: dict[str, str]) -> str | None:
    text = body.decode("utf-8", "replace").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if data is not None:
        for path in _COMMON_JSON_PATHS:
            try:
                value = _json_path(data, path)
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            if isinstance(value, (str, int, float)) and str(value).strip():
                return str(value).strip()
    for header in ("x-app-version", "x-version", "server"):
        value = headers.get(header, "").strip()
        if value and header != "server":
            return value
    match = re.search(r"(?i)(?:version|release|build)[\s\"':=]+v?([0-9]+(?:\.[0-9]+){1,4}(?:[-+._][A-Za-z0-9.-]+)?)", text[:100_000])
    return match.group(1) if match else None


def _probe_http_auto(tracker) -> tuple[str | None, int, str]:
    configured = str(tracker["version_probe_path"] or "").strip()
    paths = (configured,) if configured else _COMMON_VERSION_PATHS
    last_error: Exception | None = None
    for path in paths:
        try:
            body, headers, latency = _http_get(_base_url(tracker, path))
            return _extract_auto_version(body, headers), latency, f"HTTP {path}"
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"No automatic HTTP version endpoint responded: {last_error}")


def _probe_http_json(tracker) -> tuple[str, int, str]:
    path = str(tracker["version_probe_path"] or tracker["health_path"] or "/")
    json_path = str(tracker["version_json_path"] or "version").strip()
    body, _, latency = _http_get(_base_url(tracker, path))
    data = json.loads(body.decode("utf-8"))
    value = _json_path(data, json_path)
    if not isinstance(value, (str, int, float)) or not str(value).strip():
        raise ValueError("JSON version path did not return a scalar value.")
    return str(value).strip(), latency, f"HTTP JSON {path} → {json_path}"


def _probe_http_regex(tracker) -> tuple[str, int, str]:
    path = str(tracker["version_probe_path"] or tracker["health_path"] or "/")
    pattern = str(tracker["version_regex"] or "").strip()
    if not pattern:
        raise ValueError("A version regular expression is required.")
    body, _, latency = _http_get(_base_url(tracker, path))
    match = re.search(pattern, body.decode("utf-8", "replace"), re.MULTILINE)
    if not match:
        raise ValueError("Version regular expression did not match the response.")
    value = match.group(1) if match.groups() else match.group(0)
    return value.strip(), latency, f"HTTP regex {path}"


def _probe_ssh_docker(tracker) -> tuple[str, int, str]:
    host = _validate_host(str(tracker["install_host"] or ""))
    user = str(tracker["ssh_user"] or "").strip()
    container = str(tracker["docker_container"] or "").strip()
    key_name = str(tracker["ssh_key_name"] or "id_ed25519").strip()
    if not _USER_RE.fullmatch(user):
        raise ValueError("SSH username is invalid.")
    if not _CONTAINER_RE.fullmatch(container):
        raise ValueError("Docker container name is invalid.")
    if not _KEY_RE.fullmatch(key_name):
        raise ValueError("SSH key filename is invalid.")
    port = _port(tracker["ssh_port"], 22)
    service_latency = None
    if tracker["install_port"] not in (None, ""):
        service_latency = _connect(host, _port(tracker["install_port"]), timeout=4.0)
    ssh_dir = Path(os.environ.get("RADAR_SSH_DIR", "/ssh"))
    key_path = ssh_dir / key_name
    known_hosts = ssh_dir / "known_hosts"
    if not key_path.is_file():
        raise ValueError(f"SSH key {key_name!r} is not present in the radar SSH directory.")
    if not known_hosts.is_file():
        raise ValueError("SSH known_hosts is not configured.")
    remote_command = (
        "docker inspect --format "
        + shlex.quote('{{ index .Config.Labels "org.opencontainers.image.version" }}|{{.Config.Image}}')
        + " "
        + shlex.quote(container)
    )
    command = [
        "ssh", "-i", str(key_path), "-p", str(port),
        "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "ConnectTimeout=6", f"{user}@{host}", remote_command,
    ]
    started = time.monotonic()
    completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    latency = max(1, round((time.monotonic() - started) * 1000))
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "SSH Docker probe failed").strip()[:700])
    output = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    label, _, image = output.partition("|")
    label = label.strip()
    image = image.strip()
    reachability = f"; service port {tracker['install_port']} online" if service_latency is not None else ""
    if label and label != "<no value>":
        return label, max(latency, service_latency or 0), f"Docker label on {user}@{host}{reachability}"
    if not image:
        raise RuntimeError("Docker inspect did not return an image reference.")
    if "@sha256:" in image:
        version = image.split("@", 1)[1]
    elif ":" in image.rsplit("/", 1)[-1]:
        version = image.rsplit(":", 1)[1]
    else:
        version = image
    return version, max(latency, service_latency or 0), f"Docker image {image}{reachability}"



def _probe_portainer(tracker, *, refresh_inventory: bool = True) -> tuple[str | None, int, str]:
    service_id = tracker["portainer_service_id"]
    if service_id in (None, ""):
        raise ValueError("Portainer service mapping is not configured.")
    started = time.monotonic()
    result = sync_inventory() if refresh_inventory else None
    with connect() as conn:
        service = conn.execute(
            """
            SELECT ps.*, pe.name AS environment_name
              FROM portainer_services ps
              JOIN portainer_environments pe ON pe.endpoint_id=ps.endpoint_id
             WHERE ps.id=?
            """,
            (int(service_id),),
        ).fetchone()
    if service is None or not int(service["present"]):
        raise RuntimeError("The mapped Portainer container is no longer present.")
    state = str(service["state"] or "unknown").lower()
    if state != "running":
        raise RuntimeError(f"Portainer reports container state: {state}")
    latency = max(1, round((time.monotonic() - started) * 1000))
    version = str(service["detected_version"] or "").strip() or None
    source = f"Portainer environment {service['environment_name']} / {service['container_name']}"
    if result is not None and result.errors:
        source += "; inventory sync completed with partial errors"
    return version, latency, source

def probe_tracker(tracker_id: int, *, refresh_portainer: bool = True) -> ProbeResult:
    with connect() as conn:
        tracker = conn.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,)).fetchone()
    if tracker is None:
        raise ValueError(f"Tracker {tracker_id} does not exist.")

    now = utcnow()
    host = str(tracker["install_host"] or "").strip()
    mode = str(tracker["probe_mode"] or "manual")
    if mode != "portainer" and not host:
        result = ProbeResult(tracker_id, "unconfigured", False, tracker["installed_version"], error="Machine IP/hostname is not configured.")
    else:
        try:
            if mode == "portainer":
                version, latency, source = _probe_portainer(tracker, refresh_inventory=refresh_portainer)
            elif mode == "ssh_docker":
                version, latency, source = _probe_ssh_docker(tracker)
            elif mode == "http_auto":
                version, latency, source = _probe_http_auto(tracker)
            elif mode == "http_json":
                version, latency, source = _probe_http_json(tracker)
            elif mode == "http_regex":
                version, latency, source = _probe_http_regex(tracker)
            else:
                port = _port(tracker["install_port"], 443 if str(tracker["install_scheme"]) == "https" else 80)
                latency = _connect(_validate_host(host), port)
                version = str(tracker["installed_version"] or "").strip() or None
                source = "Manual version with TCP reachability"
            result = ProbeResult(tracker_id, "ok", True, version, latency, source=source)
        except (OSError, ValueError, RuntimeError, PortainerError, urllib.error.URLError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            result = ProbeResult(tracker_id, "error", False, tracker["detected_installed_version"] or tracker["installed_version"], error=str(exc)[:1000])

    with transaction() as conn:
        conn.execute(
            """
            UPDATE trackers
               SET detected_installed_version = CASE WHEN ? = 'ok' AND ? IS NOT NULL THEN ? ELSE detected_installed_version END,
                   last_probe_at = ?, last_probe_status = ?, last_probe_error = ?,
                   last_probe_latency_ms = ?,
                   last_seen_online_at = CASE WHEN ? = 1 THEN ? ELSE last_seen_online_at END,
                   updated_at = ?
             WHERE id = ?
            """,
            (
                result.status, result.installed_version, result.installed_version,
                now, result.status, result.error, result.latency_ms,
                int(result.online), now, now, tracker_id,
            ),
        )
    return result


def probe_all(enabled_only: bool = True) -> list[ProbeResult]:
    query = "SELECT id, probe_mode FROM trackers WHERE (probe_mode = 'portainer' OR (install_host IS NOT NULL AND trim(install_host) <> ''))"
    if enabled_only:
        query += " AND enabled = 1"
    query += " ORDER BY name COLLATE NOCASE"
    with connect() as conn:
        rows = conn.execute(query).fetchall()
    has_portainer = any(str(row["probe_mode"] or "") == "portainer" for row in rows)
    if has_portainer:
        try:
            sync_inventory()
        except PortainerError:
            # Individual probes will report stale/missing mappings without causing
            # non-Portainer services to be skipped.
            pass
    return [
        probe_tracker(int(row["id"]), refresh_portainer=False if has_portainer else True)
        for row in rows
    ]
