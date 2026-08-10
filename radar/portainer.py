from __future__ import annotations

import ipaddress
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .db import connect, get_settings, set_settings, transaction, utcnow
from .secrets_store import decrypt_secret
from .version import APP_VERSION


class PortainerError(RuntimeError):
    pass


@dataclass
class PortainerSyncResult:
    environments: int
    services: int
    linked_trackers: int
    offline_environments: int
    errors: list[str]
    synced_at: str

    @property
    def ok(self) -> bool:
        return not self.errors


def _settings() -> dict[str, str]:
    return get_settings([
        "portainer_enabled", "portainer_base_url", "portainer_api_token_enc",
        "portainer_verify_tls", "portainer_timeout", "portainer_sync_hours",
    ])


def _context(verify_tls: bool) -> ssl.SSLContext | None:
    if verify_tls:
        return None
    return ssl._create_unverified_context()  # noqa: SLF001 - explicit opt-in for self-signed LAN TLS.


def _request(path: str, *, timeout: int | None = None) -> Any:
    settings = _settings()
    base_url = (settings.get("portainer_base_url") or "").strip().rstrip("/")
    token = decrypt_secret(settings.get("portainer_api_token_enc", ""))
    if not base_url:
        raise PortainerError("Portainer base URL is not configured.")
    if not token:
        raise PortainerError("Portainer API access token is not configured.")
    if not path.startswith("/"):
        path = "/" + path
    request = urllib.request.Request(
        base_url + path,
        headers={
            "Accept": "application/json",
            "X-API-Key": token,
            "User-Agent": f"Software-Release-Radar/{APP_VERSION}",
        },
    )
    configured_timeout = int(settings.get("portainer_timeout") or 20)
    verify_tls = settings.get("portainer_verify_tls", "1") == "1"
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout or configured_timeout,
            context=_context(verify_tls),
        ) as response:
            raw = response.read(10_000_000)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", "replace")
        raise PortainerError(f"Portainer API returned HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise PortainerError(f"Unable to reach Portainer: {exc.reason}") from exc
    try:
        return json.loads(raw.decode("utf-8")) if raw else None
    except json.JSONDecodeError as exc:
        raise PortainerError("Portainer returned an invalid JSON response.") from exc


def test_connection() -> dict[str, Any]:
    started = time.monotonic()
    endpoints = _request("/api/endpoints")
    if not isinstance(endpoints, list):
        raise PortainerError("Portainer endpoint listing returned an unexpected response.")
    docker_endpoints = [item for item in endpoints if _is_docker_endpoint(item)]
    return {
        "ok": True,
        "latency_ms": max(1, round((time.monotonic() - started) * 1000)),
        "environments": len(endpoints),
        "docker_environments": len(docker_endpoints),
        "names": [str(item.get("Name") or item.get("name") or item.get("Id") or item.get("id")) for item in docker_endpoints],
    }


def _is_docker_endpoint(endpoint: dict[str, Any]) -> bool:
    endpoint_type = endpoint.get("Type", endpoint.get("type"))
    # Portainer endpoint types 1/2/4/7 are Docker-family in common CE/BE releases.
    # Also accept endpoints whose platform explicitly says Docker, then verify by API call.
    platform = str(endpoint.get("Platform") or endpoint.get("platform") or "").lower()
    return endpoint_type in {1, 2, 4, 7} or "docker" in platform


def _endpoint_id(endpoint: dict[str, Any]) -> int:
    value = endpoint.get("Id", endpoint.get("id"))
    return int(value)


def _endpoint_name(endpoint: dict[str, Any]) -> str:
    return str(endpoint.get("Name") or endpoint.get("name") or f"Environment {_endpoint_id(endpoint)}")


def _endpoint_url(endpoint: dict[str, Any]) -> str:
    return str(endpoint.get("URL") or endpoint.get("Url") or endpoint.get("url") or "")


def _endpoint_host(endpoint: dict[str, Any]) -> str | None:
    candidates = [
        endpoint.get("PublicURL"), endpoint.get("PublicUrl"), endpoint.get("URL"),
        endpoint.get("Url"), endpoint.get("url"),
    ]
    for raw in candidates:
        value = str(raw or "").strip()
        if not value:
            continue
        parsed = urllib.parse.urlparse(value if "://" in value else "tcp://" + value)
        host = parsed.hostname
        if not host or host in {"127.0.0.1", "localhost", "0.0.0.0", "host.docker.internal"}:
            continue
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        return host
    return None


def _normalise_container_name(item: dict[str, Any]) -> str:
    names = item.get("Names") or item.get("names") or []
    if names:
        return str(names[0]).lstrip("/")
    return str(item.get("Name") or item.get("name") or item.get("Id") or item.get("id") or "unknown")


def _split_image(image: str) -> tuple[str, str | None]:
    image = (image or "").strip()
    if not image:
        return "", None
    if "@sha256:" in image:
        return image.split("@", 1)[0], image.split("@", 1)[1]
    last = image.rsplit("/", 1)[-1]
    if ":" in last:
        repository, tag = image.rsplit(":", 1)
        return repository, tag
    return image, None


def _github_repository(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    raw = raw.removesuffix(".git").rstrip("/")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", raw):
        return raw
    parsed = urllib.parse.urlparse(raw if "://" in raw else "https://" + raw)
    if parsed.hostname and parsed.hostname.lower() in {"github.com", "www.github.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1].removesuffix('.git')}"
    return None


def _version_from(image: str, labels: dict[str, Any]) -> str | None:
    for key in (
        "software-release-radar.version", "software.release.radar.version",
        "org.opencontainers.image.version", "org.label-schema.version",
    ):
        value = str(labels.get(key) or "").strip()
        if value:
            return value
    _, tag = _split_image(image)
    if tag and tag.lower() not in {"latest", "main", "master", "develop", "development", "edge", "stable"}:
        return tag
    return None


def _repository_from(labels: dict[str, Any]) -> str | None:
    for key in (
        "software-release-radar.repository", "software.release.radar.repository",
        "org.opencontainers.image.source", "org.label-schema.vcs-url",
    ):
        repository = _github_repository(str(labels.get(key) or ""))
        if repository:
            return repository
    return None


def _published_ports(item: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    ports = item.get("Ports") or item.get("ports") or []
    clean: list[dict[str, Any]] = []
    first_public: int | None = None
    for port in ports:
        if not isinstance(port, dict):
            continue
        private_port = port.get("PrivatePort")
        public_port = port.get("PublicPort")
        entry = {
            "private": int(private_port) if private_port not in (None, "") else None,
            "public": int(public_port) if public_port not in (None, "") else None,
            "type": str(port.get("Type") or "tcp"),
            "ip": str(port.get("IP") or ""),
        }
        if first_public is None and entry["public"]:
            first_public = entry["public"]
        clean.append(entry)
    return clean, first_public


def _health(item: dict[str, Any]) -> str | None:
    status = str(item.get("Status") or item.get("status") or "").lower()
    match = re.search(r"\((healthy|unhealthy|starting)\)", status)
    return match.group(1) if match else None


def is_expected_offline_error(exc: PortainerError) -> bool:
    """Return True when Portainer is reporting an unreachable Docker endpoint.

    Powered-off hosts and disconnected agents are inventory state, not a fault in
    the Release Radar ↔ Portainer connection. Authentication and malformed API
    responses must still surface as real synchronisation errors.
    """
    message = str(exc).lower()
    offline_markers = (
        "no route to host",
        "connection refused",
        "connection reset by peer",
        "i/o timeout",
        "context deadline exceeded",
        "network is unreachable",
        "host is down",
        "dial tcp",
        "proxy failure",
    )
    return any(marker in message for marker in offline_markers)


def _image_labels(endpoint_id: int, image_id: str | None) -> dict[str, Any]:
    if not image_id:
        return {}
    encoded = urllib.parse.quote(str(image_id), safe="")
    try:
        payload = _request(f"/api/endpoints/{endpoint_id}/docker/images/{encoded}/json")
    except PortainerError:
        return {}
    if not isinstance(payload, dict):
        return {}
    config = payload.get("Config") or payload.get("config") or {}
    labels = config.get("Labels") or config.get("labels") or {}
    return labels if isinstance(labels, dict) else {}



def _canonicalise_service_tracker_link(conn, service, repository: str | None, *,
                                       endpoint_id: int, container_name: str,
                                       now: str):
    # Keep one canonical Portainer service per tracker and recover safe
    # container recreations. A replacement may inherit a tracker only when
    # the previous mapped service is absent and the replacement has the same
    # endpoint, container name and exact repository.
    if service is None:
        return service

    service_id = int(service["id"])
    linked_tracker_id = service["tracker_id"]

    # If historical data links one tracker to several current services, the
    # tracker's explicit portainer_service_id remains authoritative.
    if linked_tracker_id not in (None, ""):
        tracker = conn.execute(
            "SELECT id, portainer_service_id FROM trackers WHERE id=?",
            (int(linked_tracker_id),),
        ).fetchone()
        if tracker is None:
            conn.execute(
                "UPDATE portainer_services SET tracker_id=NULL, updated_at=? WHERE id=?",
                (now, service_id),
            )
        else:
            canonical_id = tracker["portainer_service_id"]
            if canonical_id not in (None, "") and int(canonical_id) != service_id:
                canonical = conn.execute(
                    "SELECT id FROM portainer_services WHERE id=?",
                    (int(canonical_id),),
                ).fetchone()
                if canonical is not None:
                    conn.execute(
                        "UPDATE portainer_services SET tracker_id=NULL, updated_at=? WHERE id=?",
                        (now, service_id),
                    )
        service = conn.execute(
            "SELECT * FROM portainer_services WHERE id=?", (service_id,)
        ).fetchone()

    if service and not service["tracker_id"] and repository:
        matches = conn.execute(
            "SELECT t.id, t.portainer_service_id "
            "FROM trackers t "
            "LEFT JOIN portainer_services mapped ON mapped.id=t.portainer_service_id "
            "WHERE t.repository=? COLLATE NOCASE "
            "AND (t.portainer_service_id IS NULL "
            "OR (mapped.id IS NOT NULL AND mapped.present=0 "
            "AND mapped.endpoint_id=? "
            "AND mapped.container_name=? COLLATE NOCASE))",
            (repository, endpoint_id, container_name),
        ).fetchall()
        if len(matches) == 1:
            matched_tracker_id = int(matches[0]["id"])
            conn.execute(
                "UPDATE portainer_services SET tracker_id=NULL, updated_at=? "
                "WHERE tracker_id=? AND id<>?",
                (now, matched_tracker_id, service_id),
            )
            conn.execute(
                "UPDATE portainer_services SET tracker_id=?, updated_at=? WHERE id=?",
                (matched_tracker_id, now, service_id),
            )
            service = conn.execute(
                "SELECT * FROM portainer_services WHERE id=?", (service_id,)
            ).fetchone()

    return service

def sync_inventory(progress: Callable[..., None] | None = None) -> PortainerSyncResult:
    settings = _settings()
    if settings.get("portainer_enabled", "0") != "1":
        raise PortainerError("Portainer integration is disabled.")
    synced_at = utcnow()
    errors: list[str] = []
    environments_count = 0
    services_count = 0
    linked_count = 0
    offline_count = 0
    endpoints = _request("/api/endpoints")
    if not isinstance(endpoints, list):
        raise PortainerError("Portainer endpoint listing returned an unexpected response.")

    seen_environment_ids: set[int] = set()
    image_label_cache: dict[tuple[int, str], dict[str, Any]] = {}
    docker_endpoints = [item for item in endpoints if isinstance(item, dict) and _is_docker_endpoint(item)]
    if progress:
        progress(total_environments=len(docker_endpoints), processed_environments=0, services_found=0, offline_environments=0, unexpected_errors=0, message="Synchronising Portainer environments")

    for endpoint in endpoints:
        if not isinstance(endpoint, dict) or not _is_docker_endpoint(endpoint):
            continue
        endpoint_id = _endpoint_id(endpoint)
        endpoint_name = _endpoint_name(endpoint)
        endpoint_url = _endpoint_url(endpoint)
        endpoint_host = _endpoint_host(endpoint)
        if progress:
            progress(current_environment=endpoint_name, message=f"Synchronising {endpoint_name}")
        seen_environment_ids.add(endpoint_id)
        environments_count += 1
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO portainer_environments
                    (endpoint_id, name, endpoint_url, host, status, endpoint_type, last_seen_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(endpoint_id) DO UPDATE SET
                    name=excluded.name, endpoint_url=excluded.endpoint_url, host=excluded.host,
                    status=excluded.status, endpoint_type=excluded.endpoint_type,
                    updated_at=excluded.updated_at
                """,
                (
                    endpoint_id, endpoint_name, endpoint_url, endpoint_host,
                    "checking",
                    str(endpoint.get("Type") or endpoint.get("type") or ""),
                    None, synced_at,
                ),
            )
        try:
            containers = _request(f"/api/endpoints/{endpoint_id}/docker/containers/json?all=1")
        except PortainerError as exc:
            expected_offline = is_expected_offline_error(exc)
            status = "offline" if expected_offline else "error"
            with transaction() as conn:
                conn.execute(
                    "UPDATE portainer_environments SET status=?, updated_at=? WHERE endpoint_id=?",
                    (status, synced_at, endpoint_id),
                )
            if expected_offline:
                offline_count += 1
            else:
                errors.append(f"{endpoint_name}: {exc}")
            if progress:
                progress(processed_environments=environments_count, services_found=services_count, offline_environments=offline_count, unexpected_errors=len(errors))
            continue
        with transaction() as conn:
            conn.execute(
                "UPDATE portainer_environments SET status='online', last_seen_at=?, updated_at=? WHERE endpoint_id=?",
                (synced_at, synced_at, endpoint_id),
            )
        if not isinstance(containers, list):
            errors.append(f"{endpoint_name}: container listing returned an unexpected response")
            continue
        # Only mark an environment's previous containers absent after its current
        # listing succeeds. A temporarily unreachable endpoint must not erase its
        # last known inventory.
        with transaction() as conn:
            conn.execute(
                "UPDATE portainer_services SET present=0, updated_at=? WHERE endpoint_id=?",
                (synced_at, endpoint_id),
            )
        for item in containers:
            if not isinstance(item, dict):
                continue
            container_id = str(item.get("Id") or item.get("id") or "").strip()
            if not container_id:
                continue
            services_count += 1
            name = _normalise_container_name(item)
            image = str(item.get("Image") or item.get("image") or "")
            image_id = str(item.get("ImageID") or item.get("ImageId") or item.get("imageID") or "")
            labels = item.get("Labels") or item.get("labels") or {}
            if not isinstance(labels, dict):
                labels = {}
            cache_key = (endpoint_id, image_id)
            if cache_key not in image_label_cache:
                image_label_cache[cache_key] = _image_labels(endpoint_id, image_id)
            merged_labels = {**image_label_cache[cache_key], **labels}
            ports, first_port = _published_ports(item)
            stack_name = str(merged_labels.get("com.docker.compose.project") or "").strip() or None
            service_name = str(merged_labels.get("com.docker.compose.service") or "").strip() or None
            repository = _repository_from(merged_labels)
            version = _version_from(image, merged_labels)
            state = str(item.get("State") or item.get("state") or "unknown")
            health = _health(item)
            source_url = str(merged_labels.get("org.opencontainers.image.source") or "").strip() or None
            digest = image.split("@", 1)[1] if "@sha256:" in image else None
            now = synced_at
            with transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO portainer_services
                        (endpoint_id, container_id, container_name, stack_name, service_name,
                         image, image_id, image_digest, detected_version, detected_repository,
                         source_url, published_ports_json, primary_port, state, health_status,
                         present, ignored, first_seen_at, last_seen_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?)
                    ON CONFLICT(endpoint_id, container_id) DO UPDATE SET
                        container_name=excluded.container_name, stack_name=excluded.stack_name,
                        service_name=excluded.service_name, image=excluded.image,
                        image_id=excluded.image_id, image_digest=excluded.image_digest,
                        detected_version=excluded.detected_version,
                        detected_repository=excluded.detected_repository,
                        source_url=excluded.source_url, published_ports_json=excluded.published_ports_json,
                        primary_port=excluded.primary_port, state=excluded.state,
                        health_status=excluded.health_status, present=1,
                        last_seen_at=excluded.last_seen_at, updated_at=excluded.updated_at
                    """,
                    (
                        endpoint_id, container_id, name, stack_name, service_name, image,
                        image_id, digest, version, repository, source_url,
                        json.dumps(ports, separators=(",", ":")), first_port,
                        state, health, now, now, now,
                    ),
                )
                service = conn.execute(
                    "SELECT * FROM portainer_services WHERE endpoint_id=? AND container_id=?",
                    (endpoint_id, container_id),
                ).fetchone()
                # Preserve explicit mappings, automatically recover safe
                # container recreations, and prevent one tracker from remaining
                # attached to several current Portainer service rows.
                service = _canonicalise_service_tracker_link(
                    conn, service, repository,
                    endpoint_id=endpoint_id, container_name=name, now=now,
                )
                if service and service["tracker_id"]:
                    tracker_id = int(service["tracker_id"])
                    effective_repository = service["repository_override"] or service["detected_repository"]
                    conn.execute(
                        """
                        UPDATE trackers SET
                            detected_installed_version=COALESCE(?, detected_installed_version),
                            machine_name=?, install_host=COALESCE(?, install_host),
                            install_port=COALESCE(?, install_port), docker_container=?,
                            probe_mode='portainer', inventory_source='portainer',
                            portainer_service_id=?, last_probe_at=?,
                            last_probe_status=?, last_probe_error=NULL,
                            last_seen_online_at=CASE WHEN ?='running' THEN ? ELSE last_seen_online_at END,
                            updated_at=?
                        WHERE id=?
                        """,
                        (
                            version, endpoint_name, endpoint_host, first_port, name,
                            int(service["id"]), now,
                            "ok" if state == "running" else "error", state, now, now, tracker_id,
                        ),
                    )
                    if effective_repository:
                        linked_count += 1
        if progress:
            progress(processed_environments=environments_count, services_found=services_count, offline_environments=offline_count, unexpected_errors=len(errors))

    with transaction() as conn:
        if seen_environment_ids:
            placeholders = ",".join("?" for _ in seen_environment_ids)
            conn.execute(
                f"UPDATE portainer_environments SET status='missing', updated_at=? "
                f"WHERE endpoint_id NOT IN ({placeholders})",
                [synced_at, *sorted(seen_environment_ids)],
            )
        else:
            conn.execute("UPDATE portainer_environments SET status='missing', updated_at=?", (synced_at,))
    if progress:
        progress(processed_environments=environments_count, services_found=services_count, offline_environments=offline_count, unexpected_errors=len(errors), current_environment=None, message="Finalising inventory")
    set_settings({
        "portainer_last_sync_at": synced_at,
        "portainer_last_sync_status": "ok" if not errors else "partial",
        "portainer_last_sync_error": "\n".join(errors)[:4000],
    })
    return PortainerSyncResult(
        environments_count, services_count, linked_count, offline_count, errors, synced_at
    )


def import_service(service_id: int, repository: str, *, name: str | None = None,
                   refresh_hours: int = 6, tags: str = "portainer,docker",
                   include_prereleases: bool = False) -> tuple[int, str]:
    repository = _github_repository(repository)
    if not repository:
        raise PortainerError("Enter a valid GitHub repository as owner/repository or a github.com URL.")
    with connect() as conn:
        service = conn.execute(
            """
            SELECT ps.*, pe.name AS environment_name, pe.host AS environment_host
              FROM portainer_services ps
              JOIN portainer_environments pe ON pe.endpoint_id = ps.endpoint_id
             WHERE ps.id = ?
            """,
            (service_id,),
        ).fetchone()
    if service is None:
        raise PortainerError("Portainer service does not exist. Run a synchronisation first.")
    tracker_name = (name or service["service_name"] or service["container_name"] or repository.split("/", 1)[1]).strip()
    now = utcnow()
    with transaction() as conn:
        existing = conn.execute("SELECT * FROM trackers WHERE repository=? COLLATE NOCASE", (repository,)).fetchone()
        if existing:
            tracker_id = int(existing["id"])
            conn.execute(
                """
                UPDATE trackers SET name=?, enabled=1, tags=?, refresh_hours=?,
                    installed_version=COALESCE(?, installed_version),
                    detected_installed_version=COALESCE(?, detected_installed_version),
                    machine_name=?, install_host=COALESCE(?, install_host),
                    install_port=COALESCE(?, install_port), docker_container=?,
                    probe_mode='portainer', inventory_source='portainer',
                    portainer_service_id=?, include_prereleases=?, updated_at=?
                WHERE id=?
                """,
                (
                    tracker_name, tags, refresh_hours, service["detected_version"],
                    service["detected_version"], service["environment_name"],
                    service["environment_host"], service["primary_port"],
                    service["container_name"], service_id, int(include_prereleases), now, tracker_id,
                ),
            )
            action = "updated"
        else:
            cursor = conn.execute(
                """
                INSERT INTO trackers
                    (name, repository, strategy, include_prereleases, enabled, tags,
                     refresh_hours, installed_version, detected_installed_version,
                     machine_name, install_host, install_port, install_scheme,
                     probe_mode, docker_container, portainer_service_id,
                     inventory_source, created_at, updated_at)
                VALUES (?, ?, 'release', ?, 1, ?, ?, ?, ?, ?, ?, ?, 'http',
                        'portainer', ?, ?, 'portainer', ?, ?)
                """,
                (
                    tracker_name, repository, int(include_prereleases), tags,
                    refresh_hours, service["detected_version"], service["detected_version"],
                    service["environment_name"], service["environment_host"],
                    service["primary_port"], service["container_name"], service_id,
                    now, now,
                ),
            )
            tracker_id = int(cursor.lastrowid)
            action = "added"
        conn.execute(
            """
            UPDATE portainer_services
               SET tracker_id=NULL, updated_at=?
             WHERE tracker_id=? AND id<>?
            """,
            (now, tracker_id, service_id),
        )
        conn.execute(
            """
            UPDATE portainer_services SET tracker_id=?, repository_override=?, updated_at=?
             WHERE id=?
            """,
            (tracker_id, repository, now, service_id),
        )
    return tracker_id, action



def import_services_batch(items: list[dict[str, Any]], *, refresh_hours: int = 6,
                          tags: str = "portainer,docker",
                          include_prereleases: bool = False,
                          progress: Callable[..., None] | None = None) -> dict[str, Any]:
    """Import many Portainer services without blocking the browser request.

    The worker performs the imports sequentially against SQLite for reliability.
    The user-facing speed improvement comes from queueing the work immediately and
    reporting progress instead of keeping a reverse-proxy request open.
    """
    imported: list[dict[str, Any]] = []
    failures: list[str] = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        service_id = int(item["service_id"])
        name = str(item.get("name") or "").strip() or None
        repository = str(item.get("repository") or "").strip()
        if progress:
            progress(
                total_items=total,
                processed_items=index - 1,
                imported_items=len(imported),
                failed_items=len(failures),
                current_item=name or f"Service {service_id}",
                message=f"Importing {index} of {total}",
            )
        try:
            tracker_id, action = import_service(
                service_id,
                repository,
                name=name,
                refresh_hours=refresh_hours,
                tags=tags,
                include_prereleases=include_prereleases,
            )
            imported.append({
                "service_id": service_id,
                "tracker_id": tracker_id,
                "action": action,
                "name": name or f"Service {service_id}",
            })
        except (ValueError, PortainerError) as exc:
            failures.append(f"{name or f'Service {service_id}'}: {exc}")
        if progress:
            progress(
                total_items=total,
                processed_items=index,
                imported_items=len(imported),
                failed_items=len(failures),
            )
    return {"imported": imported, "failures": failures}

def ignore_service(service_id: int, ignored: bool = True) -> None:
    with transaction() as conn:
        result = conn.execute(
            "UPDATE portainer_services SET ignored=?, updated_at=? WHERE id=?",
            (int(ignored), utcnow(), service_id),
        )
        if result.rowcount != 1:
            raise PortainerError("Portainer service does not exist.")


def inventory_summary() -> dict[str, Any]:
    with connect() as conn:
        environments = conn.execute(
            "SELECT * FROM portainer_environments ORDER BY name COLLATE NOCASE"
        ).fetchall()
        services = conn.execute(
            """
            SELECT ps.*, pe.name AS environment_name, pe.host AS environment_host,
                   t.name AS tracker_name, t.repository AS tracker_repository
              FROM portainer_services ps
              JOIN portainer_environments pe ON pe.endpoint_id=ps.endpoint_id
              LEFT JOIN trackers t ON t.id=ps.tracker_id
             ORDER BY pe.name COLLATE NOCASE, COALESCE(ps.stack_name,''), ps.container_name COLLATE NOCASE
            """
        ).fetchall()
    environment_items = [dict(row) for row in environments]
    service_items = [dict(row) for row in services]
    return {
        "environments": environment_items,
        "services": service_items,
        "environment_counts": {
            "online": sum(1 for item in environment_items if item.get("status") == "online"),
            "offline": sum(1 for item in environment_items if item.get("status") == "offline"),
            "error": sum(1 for item in environment_items if item.get("status") == "error"),
        },
    }
