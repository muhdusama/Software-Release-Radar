"""Read-only REST API, Prometheus metrics and the maintenance calendar feed.

The REST endpoints reuse the MCP read tools, so they share one projection,
one permission model and one result-size bound. Requests authenticate with an
API key from Profile (``Authorization: Bearer srr_...``) or with the browser
session. Nothing here changes stored data.
"""
from __future__ import annotations

import hmac
from datetime import date, datetime, timedelta, timezone

from flask import Flask, Response, abort, g, jsonify, request, url_for
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError, validate_call

from . import mcp_tools
from .auth import token_digest
from .auth_rate_limit import _key, _record_failure, _remaining_seconds
from .build_info import build_commit
from .db import connect
from .github import shared_rate_limit_until
from .mcp_auth import Principal, RadarTokenVerifier, principal_for_key, request_principal
from .tracker_utils import parse_utc
from .upgrade_workflow import DECISION_CHOICES
from .version import APP_VERSION
from .versioning import classify_tracker_state

API_KEY_FAILURE_THRESHOLD = 20
CALENDAR_TOKEN_PREFIX = "cal_"


class _BadRequest(ValueError):
    pass


def _authenticate(secret_key: str) -> tuple[Principal | None, Response | None]:
    header = request.headers.get("Authorization", "")
    if not header:
        if g.get("user") is None:
            return None, _error(401, "Authentication required.")
        return Principal("", int(g.user["id"]), g.user["role"] == "admin", frozenset({"read"})), None
    scheme, _, token = header.partition(" ")
    throttle = _key(secret_key, "api-key-ip", request.remote_addr or "unknown")
    if _remaining_seconds([throttle]):
        return None, _error(429, "Too many failed API key attempts. Try again later.")
    access = RadarTokenVerifier()._verify(token.strip()) if scheme.lower() == "bearer" else None
    if access is None:
        _record_failure(throttle, API_KEY_FAILURE_THRESHOLD)
        return None, _error(401, "API key is invalid, expired or revoked.")
    try:
        return principal_for_key(access.client_id), None
    except ValueError:
        return None, _error(401, "API key is invalid, expired or revoked.")


def _error(status: int, message: str) -> Response:
    response = jsonify({"error": message})
    response.status_code = status
    if status == 401:
        response.headers["WWW-Authenticate"] = 'Bearer realm="Software Release Radar"'
    response.headers["Cache-Control"] = "no-store"
    return response


def _int_arg(name: str) -> int | None:
    value = request.args.get(name)
    if value is None or value == "":
        return None
    if not value.isascii() or not value.isdecimal() or len(value) > 12:
        raise _BadRequest(name)
    return int(value)


def _bool_arg(name: str) -> bool | None:
    value = request.args.get(name)
    if value is None or value == "":
        return None
    lowered = value.lower()
    if lowered not in {"true", "false", "1", "0"}:
        raise _BadRequest(name)
    return lowered in {"true", "1"}


def _str_arg(name: str) -> str | None:
    value = request.args.get(name)
    return value if value not in (None, "") else None


def _clean(values: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value is not None}


def install_api(app: Flask) -> None:
    secret_key = str(app.secret_key or "")

    def call(tool, params_factory):
        principal, failure = _authenticate(secret_key)
        if failure is not None:
            return failure
        try:
            params = _clean(params_factory())
        except _BadRequest as exc:
            return _error(400, f"Invalid query parameter: {exc}.")
        token = request_principal.set(principal)
        try:
            result = validate_call(tool)(**params)
        except ValidationError:
            return _error(400, "Invalid query parameters.")
        except PermissionError:
            return _error(403, "This key or account cannot read that resource.")
        except ToolError as exc:
            message = str(exc)
            status = 404 if message.startswith("Not found") else 400 if message.startswith("Invalid") else 503
            return _error(status, message)
        finally:
            request_principal.reset(token)
        response = jsonify(result)
        response.headers["Cache-Control"] = "no-store"
        return response

    def page_args():
        return {"limit": _int_arg("limit"), "after_id": _int_arg("after_id")}

    @app.get("/api/v1/status")
    def api_status():
        return call(mcp_tools.radar_status, dict)

    @app.get("/api/v1/trackers")
    def api_trackers():
        return call(mcp_tools.trackers_list, lambda: {**page_args(), "enabled": _bool_arg("enabled"),
                                                     "tag": _str_arg("tag"), "query": _str_arg("q")})

    @app.get("/api/v1/trackers/<int:tracker_id>")
    def api_tracker(tracker_id: int):
        return call(mcp_tools.tracker_get, lambda: {"tracker_id": tracker_id})

    @app.get("/api/v1/trackers/<int:tracker_id>/releases")
    def api_tracker_releases(tracker_id: int):
        return call(mcp_tools.releases_list, lambda: {**page_args(), "tracker_id": tracker_id})

    @app.get("/api/v1/trackers/<int:tracker_id>/upgrade")
    def api_tracker_upgrade(tracker_id: int):
        return call(mcp_tools.upgrade_get, lambda: {"tracker_id": tracker_id, "release_key": _str_arg("release_key")})

    @app.get("/api/v1/history")
    def api_history():
        return call(mcp_tools.history_list, lambda: {**page_args(), "tracker_id": _int_arg("tracker_id"),
                                                     "since": _str_arg("since")})

    @app.get("/api/v1/upgrades")
    def api_upgrades():
        return call(mcp_tools.upgrades_list, lambda: {**page_args(), "decision_status": _str_arg("decision_status")})

    @app.get("/metrics")
    def metrics():
        principal, failure = _authenticate(secret_key)
        if failure is not None:
            return failure
        response = Response(render_metrics(), mimetype="text/plain")
        response.headers["Content-Type"] = "text/plain; version=0.0.4; charset=utf-8"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/calendar/<token>.ics")
    def calendar_feed(token: str):
        user = calendar_user(token)
        if user is None:
            abort(404)
        response = Response(render_calendar(lambda tracker_id: url_for(
            "upgrade_decision", tracker_id=tracker_id, _external=True)), mimetype="text/calendar")
        response.headers["Content-Type"] = "text/calendar; charset=utf-8"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Disposition"] = 'inline; filename="software-release-radar.ics"'
        return response


# --------------------------------------------------------------------------
# Prometheus metrics
# --------------------------------------------------------------------------

def _label(value: object) -> str:
    text = str(value if value is not None else "")[:200]
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _timestamp(value: str | None) -> float | None:
    parsed = parse_utc(value)
    return parsed.timestamp() if parsed else None


def render_metrics() -> str:
    with connect() as conn:
        trackers = [dict(row) for row in conn.execute("SELECT * FROM trackers ORDER BY id").fetchall()]
        decisions = dict(conn.execute(
            "SELECT d.decision_status, COUNT(*) FROM upgrade_decisions d JOIN trackers t ON t.id = d.tracker_id "
            "WHERE d.release_version = COALESCE(NULLIF(t.current_version, ''), t.current_release_name) "
            "GROUP BY d.decision_status").fetchall())
        pending = conn.execute("SELECT COUNT(*) FROM events WHERE notified_at IS NULL").fetchone()[0]
    cooldown = shared_rate_limit_until()
    cooldown_seconds = max(0.0, (cooldown - datetime.now(timezone.utc)).total_seconds()) if cooldown else 0.0

    lines: list[str] = []

    def family(name: str, kind: str, help_text: str, samples: list[tuple[dict[str, object], float]]):
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {kind}")
        for labels, value in samples:
            rendered = ",".join(f'{key}="{_label(val)}"' for key, val in labels.items())
            number = str(int(value)) if float(value).is_integer() else repr(float(value))
            lines.append(f"{name}{{{rendered}}} {number}" if rendered else f"{name} {number}")

    family("srr_build_info", "gauge", "Software Release Radar build.",
           [({"version": APP_VERSION, "commit": build_commit() or ""}, 1)])
    enabled = [t for t in trackers if t["enabled"]]
    family("srr_trackers", "gauge", "Tracked software by state.",
           [({"state": "enabled"}, len(enabled)), ({"state": "disabled"}, len(trackers) - len(enabled))])

    up, updates, checked, probe_up, latency = [], [], [], [], []
    update_count = attention_count = 0
    for tracker in enabled:
        labels = {"tracker_id": tracker["id"], "name": tracker["name"], "repository": tracker["repository"]}
        state = classify_tracker_state(tracker)
        update_count += int(state["update_available"])
        attention_count += int(state["needs_attention"])
        up.append((labels, 1 if tracker["last_status"] == "ok" else 0))
        updates.append((labels, 1 if state["update_available"] else 0))
        last_checked = _timestamp(tracker["last_checked_at"])
        if last_checked is not None:
            checked.append((labels, last_checked))
        if tracker["last_probe_status"]:
            probe_up.append((labels, 0 if tracker["last_probe_status"] == "error" else 1))
            if tracker["last_probe_latency_ms"] is not None:
                latency.append((labels, float(tracker["last_probe_latency_ms"])))

    family("srr_tracker_check_success", "gauge", "1 when the last upstream release check succeeded.", up)
    family("srr_tracker_update_available", "gauge", "1 when a newer upstream release than the installed version exists.", updates)
    family("srr_tracker_last_checked_timestamp_seconds", "gauge", "Unix time of the last upstream release check.", checked)
    family("srr_tracker_probe_up", "gauge", "1 when the last service probe succeeded.", probe_up)
    family("srr_tracker_probe_latency_milliseconds", "gauge", "Latency of the last service probe.", latency)
    family("srr_updates_available", "gauge", "Enabled trackers with a confirmed update available.", [({}, update_count)])
    family("srr_trackers_needing_attention", "gauge", "Enabled trackers with checker, probe or version-data problems.", [({}, attention_count)])
    family("srr_upgrade_decisions", "gauge", "Decisions for each tracker's current release, by status.",
           [({"status": status}, decisions.get(status, 0)) for status, _ in DECISION_CHOICES])
    family("srr_pending_notifications", "gauge", "Detected releases not yet notified.", [({}, pending)])
    family("srr_github_rate_limit_cooldown_seconds", "gauge", "Seconds until GitHub checks resume after a rate limit.",
           [({}, round(cooldown_seconds))])
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Maintenance calendar (ICS)
# --------------------------------------------------------------------------

def calendar_user(token: str):
    if not token.startswith(CALENDAR_TOKEN_PREFIX) or len(token) > 100:
        return None
    digest = token_digest(token)
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE calendar_token_digest = ? AND active = 1", (digest,)).fetchone()
    if row is None or not hmac.compare_digest(str(row["calendar_token_digest"]), digest):
        return None
    return row


def _ics_text(value: object) -> str:
    text = str(value or "")
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n"))


def _fold(line: str) -> list[str]:
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return [line]
    parts, current = [], ""
    for char in line:
        limit = 75 if not parts else 74
        if len((current + char).encode("utf-8")) > limit:
            parts.append(current)
            current = char
        else:
            current += char
    parts.append(current)
    return [parts[0]] + [" " + part for part in parts[1:]]


def render_calendar(decision_url) -> str:
    """All-day events for planned upgrades of each tracker's current release."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.tracker_id, d.release_version, d.decision_status, d.priority, d.risk,
                   d.maintenance_date, d.updated_at, t.name, t.machine_name
              FROM upgrade_decisions d JOIN trackers t ON t.id = d.tracker_id
             WHERE d.maintenance_date IS NOT NULL AND d.decision_status IN ('review', 'update', 'wait')
               AND d.release_version = COALESCE(NULLIF(t.current_version, ''), t.current_release_name)
             ORDER BY d.maintenance_date, t.name COLLATE NOCASE
            """
        ).fetchall()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    labels = dict(DECISION_CHOICES)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Software Release Radar//Maintenance calendar//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Software Release Radar maintenance"]
    for row in rows:
        try:
            day = date.fromisoformat(row["maintenance_date"])
        except ValueError:
            continue
        machine = f" on {row['machine_name']}" if row["machine_name"] else ""
        description = (f"Decision: {labels.get(row['decision_status'], row['decision_status'])}. "
                       f"Priority: {row['priority']}. Risk: {row['risk']}.\n{decision_url(row['tracker_id'])}")
        lines += ["BEGIN:VEVENT", f"UID:srr-decision-{row['id']}@software-release-radar", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
                  f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
                  f"SUMMARY:{_ics_text(f'Upgrade {row['name']} to {row['release_version']}{machine}')}",
                  f"DESCRIPTION:{_ics_text(description)}", f"URL:{_ics_text(decision_url(row['tracker_id']))}",
                  "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "".join(folded + "\r\n" for line in lines for folded in _fold(line))
