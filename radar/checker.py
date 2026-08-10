from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from typing import Iterable

from .db import connect, init_db, transaction, utcnow
from .github import GitHubError, ReleaseInfo, get_latest
from .notifications import dispatch_release_notifications
from .portainer import PortainerError, sync_inventory
from .probes import probe_tracker
from .tracker_utils import is_due
from .auto_analysis import auto_analyse_event


@dataclass
class CheckResult:
    tracker_id: int
    name: str
    repository: str
    status: str
    version: str | None = None
    release_name: str | None = None
    previous_version: str | None = None
    previous_release_name: str | None = None
    changed: bool = False
    baseline: bool = False
    skipped: bool = False
    error: str | None = None
    newly_failed: bool = False
    event_id: int | None = None
    probe_status: str | None = None
    installed_version: str | None = None


def _record_success(tracker, release: ReleaseInfo, baseline: bool = False) -> CheckResult:
    now = utcnow()
    old_version = tracker["current_version"]
    old_release_name = tracker["current_release_name"]
    changed = bool(old_version and old_version != release.version)
    is_baseline = baseline or not old_version
    event_id: int | None = None

    with transaction() as conn:
        conn.execute(
            """
            UPDATE trackers
               SET current_version = ?, current_release_name = ?, current_release_url = ?,
                   current_release_body = ?, current_published_at = ?, last_checked_at = ?,
                   last_status = 'ok', last_error = NULL, updated_at = ?
             WHERE id = ?
            """,
            (release.version, release.name, release.url, release.body, release.published_at, now, now, tracker["id"]),
        )
        if changed and not is_baseline:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO events
                    (tracker_id, version, release_name, release_body, previous_version,
                     previous_release_name, release_url, published_at, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tracker["id"], release.version, release.name, release.body,
                    old_version, old_release_name, release.url, release.published_at, now,
                ),
            )
            if cursor.rowcount:
                event_id = int(cursor.lastrowid)
            else:
                row = conn.execute(
                    "SELECT id FROM events WHERE tracker_id = ? AND version = ?",
                    (tracker["id"], release.version),
                ).fetchone()
                event_id = int(row["id"]) if row else None

    result = CheckResult(
        tracker_id=tracker["id"], name=tracker["name"], repository=tracker["repository"],
        status="ok", version=release.version, release_name=release.name,
        previous_version=old_version, previous_release_name=old_release_name,
        changed=changed and not is_baseline, baseline=is_baseline, event_id=event_id,
    )
    if event_id is not None:
        auto_analyse_event(event_id)
    return result


def _record_error(tracker, message: str) -> CheckResult:
    now = utcnow()
    newly_failed = tracker["last_status"] != "error"
    with transaction() as conn:
        conn.execute(
            """
            UPDATE trackers SET last_checked_at = ?, last_status = 'error', last_error = ?, updated_at = ?
             WHERE id = ?
            """,
            (now, message[:1000], now, tracker["id"]),
        )
    return CheckResult(
        tracker_id=tracker["id"], name=tracker["name"], repository=tracker["repository"],
        status="error", error=message, newly_failed=newly_failed,
    )


def check_tracker(tracker_id: int, baseline: bool = False, run_probe: bool = True, *, refresh_portainer: bool = True) -> CheckResult:
    init_db()
    with connect() as conn:
        tracker = conn.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,)).fetchone()
    if tracker is None:
        raise ValueError(f"Tracker {tracker_id} does not exist.")

    try:
        release = get_latest(tracker["repository"], tracker["strategy"], bool(tracker["include_prereleases"]))
        result = _record_success(tracker, release, baseline=baseline)
    except (GitHubError, ValueError) as exc:
        result = _record_error(tracker, str(exc))
    except Exception as exc:  # pragma: no cover
        result = _record_error(tracker, f"Unexpected checker error: {exc}")

    if run_probe and (str(tracker["probe_mode"] or "") == "portainer" or str(tracker["install_host"] or "").strip()):
        try:
            probe = probe_tracker(tracker_id, refresh_portainer=refresh_portainer)
            result.probe_status = probe.status
            result.installed_version = probe.installed_version
        except Exception as exc:  # release checking must not fail because a service probe failed
            result.probe_status = "error"
            result.installed_version = tracker["detected_installed_version"] or tracker["installed_version"]
    return result


def check_all(enabled_only: bool = True, baseline: bool = False, due_only: bool = False) -> list[CheckResult]:
    init_db()
    query = "SELECT * FROM trackers"
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY name COLLATE NOCASE"
    with connect() as conn:
        trackers = conn.execute(query).fetchall()
    selected = trackers
    if due_only:
        selected = [row for row in trackers if is_due(row["last_checked_at"], int(row["refresh_hours"] or 6))]
    has_portainer = any(str(row["probe_mode"] or "") == "portainer" for row in selected)
    if has_portainer:
        try:
            sync_inventory()
        except PortainerError:
            # Release checks remain useful even when Portainer is temporarily
            # unavailable; mapped probes will report their own status.
            pass
    return [
        check_tracker(
            int(row["id"]), baseline=baseline,
            refresh_portainer=False if has_portainer else True,
        )
        for row in selected
    ]


def pending_events():
    with connect() as conn:
        return conn.execute(
            """
            SELECT e.*, t.name, t.repository, t.tags, t.machine_name, t.install_host,
                   t.installed_version, t.detected_installed_version
              FROM events e JOIN trackers t ON t.id = e.tracker_id
             WHERE e.notified_at IS NULL ORDER BY e.detected_at, e.id
            """
        ).fetchall()


def mark_notified(event_ids: Iterable[int]) -> None:
    ids = list(event_ids)
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    with transaction() as conn:
        conn.execute(f"UPDATE events SET notified_at = ? WHERE id IN ({placeholders})", [utcnow(), *ids])


def build_notification(events, new_errors: list[CheckResult]) -> str:
    lines: list[str] = []
    if events:
        lines.extend(["Software Release Radar", ""])
        for event in events:
            release = str(event["release_name"] or event["version"] or "unknown release")
            lines.append(f"• {event['name']}: {release}")
            previous = str(event["previous_release_name"] or event["previous_version"] or "").strip()
            if previous:
                lines.append(f"  Updated from: {previous}")
            if event["version"] and str(event["version"]).casefold() != release.casefold():
                lines.append(f"  Git tag: {event['version']}")
            installed = event["detected_installed_version"] or event["installed_version"]
            if installed:
                lines.append(f"  Installed: {installed}")
            if event["machine_name"] or event["install_host"]:
                lines.append(f"  Machine: {event['machine_name'] or event['install_host']}")
            if event["tags"]:
                lines.append(f"  Tags: {str(event['tags']).replace(',', ', ')}")
            if event["release_url"]:
                lines.append(f"  {event['release_url']}")
    if new_errors:
        if lines:
            lines.append("")
        else:
            lines.extend(["Software Release Radar", ""])
        lines.append("New checker errors:")
        for result in new_errors:
            lines.append(f"• {result.name}: {result.error}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check tracked software releases.")
    parser.add_argument("--tracker-id", type=int)
    parser.add_argument("--notify", action="store_true", help="Send SMTP/Pushover and print pending alerts to the console.")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--due", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results = [check_tracker(args.tracker_id, baseline=args.baseline)] if args.tracker_id else check_all(True, args.baseline, args.due)

    if args.json:
        print(json.dumps([asdict(item) for item in results], indent=2))
        return 1 if any(item.status == "error" for item in results) else 0

    if args.notify:
        events = pending_events()
        try:
            dispatch_release_notifications([int(event["id"]) for event in events])
        except Exception as exc:
            print(f"Software Release Radar notification dispatch warning: {exc}", file=sys.stderr)
        new_errors = [item for item in results if item.status == "error" and item.newly_failed]
        message = build_notification(events, new_errors)
        if message:
            print(message)
            sys.stdout.flush()
            mark_notified([event["id"] for event in events])
        return 0

    for result in results:
        if result.status == "ok":
            label = "new" if result.changed else "current"
            display = result.release_name or result.version
            suffix = f" [tag {result.version}]" if result.release_name and result.version and result.release_name.casefold() != result.version.casefold() else ""
            print(f"{result.name}: {display}{suffix} ({label})")
        else:
            print(f"{result.name}: ERROR: {result.error}", file=sys.stderr)
    return 1 if any(item.status == "error" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
