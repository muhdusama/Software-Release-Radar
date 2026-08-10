from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from urllib.parse import urlparse

from .analysis_service import analyse_tracker, ask_tracker
from .checker import check_all, check_tracker
from .db import audit, connect, get_setting, init_db, transaction, utcnow
from .github import normalise_repository
from .probes import probe_all, probe_tracker
from .portainer import import_service, inventory_summary, sync_inventory, test_connection as portainer_test_connection
from .notifications import notification_smoke_test
from .tracker_utils import normalise_tags, parse_utc, split_tags, validate_refresh_hours
from .upgrade_workflow import (
    DECISION_VALUES, PRIORITY_VALUES, RISK_VALUES, checklist_json,
    checklist_summary, load_checklist, release_key, validate_change_record_url,
    validate_choice, validate_maintenance_date,
)
from .version import APP_VERSION
from .versioning import classify_tracker_state, summarise_tracker_states


def _safe_optional_url(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Homepage must be a complete http:// or https:// URL.")
    return value


def _row_dict(row) -> dict:
    result = dict(row)
    result["tags"] = split_tags(result.get("tags"))
    result["include_prereleases"] = bool(result.get("include_prereleases"))
    result["enabled"] = bool(result.get("enabled"))
    result.update(classify_tracker_state(result))
    return result


def _tracker(*, repository: str | None = None, tracker_id: int | None = None):
    if repository is None and tracker_id is None:
        raise ValueError("A repository or tracker ID is required.")
    with connect() as conn:
        if tracker_id is not None:
            row = conn.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,)).fetchone()
        else:
            repo = normalise_repository(repository or "")
            row = conn.execute(
                "SELECT * FROM trackers WHERE repository = ? COLLATE NOCASE", (repo,)
            ).fetchone()
    if row is None:
        raise ValueError("The requested software is not being tracked.")
    return row


def _target_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--repository")
    group.add_argument("--tracker-id", type=int)


def track(args: argparse.Namespace) -> int:
    init_db()
    repository = normalise_repository(args.repository)
    now = utcnow()
    requested_tags = normalise_tags(args.tags)
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM trackers WHERE repository = ? COLLATE NOCASE", (repository,)
        ).fetchone()

    if existing:
        old = dict(existing)
        strategy = args.strategy or old["strategy"]
        include_prereleases = (
            int(args.include_prereleases)
            if args.include_prereleases is not None
            else int(old["include_prereleases"])
        )
        refresh_hours = (
            validate_refresh_hours(args.refresh_hours)
            if args.refresh_hours is not None
            else int(old["refresh_hours"] or 6)
        )
        tags = (
            requested_tags
            if args.replace_tags
            else normalise_tags([*split_tags(old.get("tags")), *split_tags(requested_tags)])
        )
        name = args.name.strip() if args.name else old["name"]
        values = {
            "name": name,
            "strategy": strategy,
            "include_prereleases": include_prereleases,
            "enabled": 1,
            "homepage_url": (
                _safe_optional_url(args.homepage_url)
                if args.homepage_url is not None
                else old["homepage_url"]
            ),
            "notes": args.notes if args.notes is not None else old["notes"],
            "tags": tags,
            "refresh_hours": refresh_hours,
            "installed_version": (
                args.installed_version
                if args.installed_version is not None
                else old["installed_version"]
            ),
            "machine_name": (
                args.machine_name if args.machine_name is not None else old["machine_name"]
            ),
            "install_host": args.host if args.host is not None else old["install_host"],
            "install_port": args.port if args.port is not None else old["install_port"],
            "install_scheme": args.scheme if args.scheme is not None else old["install_scheme"],
            "probe_mode": args.probe_mode if args.probe_mode is not None else old["probe_mode"],
            "docker_container": (
                args.container if args.container is not None else old["docker_container"]
            ),
            "ssh_user": args.ssh_user if args.ssh_user is not None else old["ssh_user"],
            "ssh_key_name": (
                args.ssh_key_name if args.ssh_key_name is not None else old["ssh_key_name"]
            ),
        }
        source_changed = (
            strategy != old["strategy"]
            or include_prereleases != int(old["include_prereleases"])
        )
        with transaction() as conn:
            assignments = ",".join(f"{key} = ?" for key in values)
            conn.execute(
                f"UPDATE trackers SET {assignments}, updated_at = ? WHERE id = ?",
                [*values.values(), now, old["id"]],
            )
            if source_changed:
                conn.execute(
                    """UPDATE trackers SET current_version=NULL,current_release_name=NULL,
                       current_release_url=NULL,current_release_body=NULL,current_published_at=NULL
                       WHERE id=?""",
                    (old["id"],),
                )
        result = check_tracker(int(old["id"]), baseline=source_changed)
        audit(None, "cli_tracker_updated", "tracker", old["id"], repository)
        print(
            json.dumps(
                {
                    "ok": result.status == "ok",
                    "action": "updated",
                    "tracker_id": int(old["id"]),
                    "repository": repository,
                    "check": asdict(result),
                },
                indent=2,
            )
        )
        return 0 if result.status == "ok" else 2

    name = (args.name or repository.split("/", 1)[1]).strip()
    default_refresh = int(get_setting("default_refresh_hours", "6") or 6)
    refresh_hours = validate_refresh_hours(
        args.refresh_hours if args.refresh_hours is not None else default_refresh
    )
    with transaction() as conn:
        cursor = conn.execute(
            """
            INSERT INTO trackers
                (name, repository, strategy, include_prereleases, enabled, homepage_url,
                 notes, tags, refresh_hours, installed_version, machine_name, install_host,
                 install_port, install_scheme, probe_mode, docker_container, ssh_user,
                 ssh_key_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                repository,
                args.strategy or "release",
                int(bool(args.include_prereleases)),
                _safe_optional_url(args.homepage_url),
                args.notes,
                requested_tags,
                refresh_hours,
                args.installed_version,
                args.machine_name,
                args.host,
                args.port,
                args.scheme or "http",
                args.probe_mode or "manual",
                args.container,
                args.ssh_user,
                args.ssh_key_name,
                now,
                now,
            ),
        )
        tracker_id = int(cursor.lastrowid)
    result = check_tracker(tracker_id, baseline=True)
    audit(None, "cli_tracker_added", "tracker", tracker_id, repository)
    print(
        json.dumps(
            {
                "ok": result.status == "ok",
                "action": "added",
                "tracker_id": tracker_id,
                "repository": repository,
                "check": asdict(result),
            },
            indent=2,
        )
    )
    return 0 if result.status == "ok" else 2


def list_trackers(_: argparse.Namespace) -> int:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM trackers ORDER BY name COLLATE NOCASE").fetchall()
    print(json.dumps([_row_dict(row) for row in rows], indent=2))
    return 0


def show(args: argparse.Namespace) -> int:
    row = _tracker(repository=args.repository, tracker_id=args.tracker_id)
    result = _row_dict(row)
    with connect() as conn:
        result["recent_events"] = [
            dict(event)
            for event in conn.execute(
                "SELECT * FROM events WHERE tracker_id = ? ORDER BY detected_at DESC, id DESC LIMIT 10",
                (row["id"],),
            ).fetchall()
        ]
        analysis = conn.execute(
            "SELECT * FROM ai_analyses WHERE tracker_id = ? ORDER BY id DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        decision = conn.execute(
            """SELECT * FROM upgrade_decisions WHERE tracker_id = ?
               AND release_version = COALESCE(NULLIF(?, ''), ?)""",
            (row["id"], row["current_version"], row["current_release_name"]),
        ).fetchone()
    result["latest_analysis"] = dict(analysis) if analysis else None
    result["upgrade_decision"] = dict(decision) if decision else None
    print(json.dumps(result, indent=2))
    return 0


def status(_: argparse.Namespace) -> int:
    init_db()
    with connect() as conn:
        totals = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) AS enabled,
                      SUM(CASE WHEN enabled = 0 THEN 1 ELSE 0 END) AS paused,
                      SUM(CASE WHEN last_probe_status = 'ok' THEN 1 ELSE 0 END) AS online
                 FROM trackers"""
        ).fetchone()
        pending = conn.execute(
            "SELECT COUNT(*) FROM events WHERE notified_at IS NULL"
        ).fetchone()[0]
        latest = conn.execute(
            "SELECT MAX(last_checked_at) AS last_checked_at, MAX(last_probe_at) AS last_probe_at FROM trackers"
        ).fetchone()
        rows = conn.execute(
            """SELECT t.*, d.decision_status, d.priority AS decision_priority
                 FROM trackers t LEFT JOIN upgrade_decisions d
                   ON d.tracker_id = t.id
                  AND d.release_version = COALESCE(NULLIF(t.current_version, ''), t.current_release_name)"""
        ).fetchall()

    raw_rows = [dict(row) for row in rows]
    state_counts = summarise_tracker_states(raw_rows)
    upgrade_decisions = {key: 0 for key in ("review", "update", "wait", "ignore", "deployed")}
    for row in raw_rows:
        state = classify_tracker_state(row)
        if not state["update_available"]:
            continue
        decision_status = row.get("decision_status") or "review"
        upgrade_decisions[decision_status] = upgrade_decisions.get(decision_status, 0) + 1

    result = {
        "ok": True,
        "name": "Software Release Radar",
        "version": APP_VERSION,
        "trackers": {
            "total": int(totals["total"] or 0),
            "enabled": int(totals["enabled"] or 0),
            "paused": int(totals["paused"] or 0),
            "online": int(totals["online"] or 0),
            **state_counts,
        },
        "pending_alerts": int(pending or 0),
        "upgrade_decisions": upgrade_decisions,
        "last_checked_at": latest["last_checked_at"],
        "last_probe_at": latest["last_probe_at"],
        "ai_enabled": get_setting("openai_enabled", "0") == "1",
        "auto_analysis_enabled": get_setting("openai_auto_analyse", "0") == "1",
    }
    print(json.dumps(result, indent=2))
    return 0


def check(args: argparse.Namespace) -> int:
    if args.repository or args.tracker_id:
        row = _tracker(repository=args.repository, tracker_id=args.tracker_id)
        results = [check_tracker(int(row["id"]))]
    else:
        results = check_all(enabled_only=True, due_only=args.due)
    print(json.dumps([asdict(result) for result in results], indent=2))
    return 1 if any(result.status == "error" for result in results) else 0


def probe(args: argparse.Namespace) -> int:
    if args.repository or args.tracker_id:
        row = _tracker(repository=args.repository, tracker_id=args.tracker_id)
        results = [probe_tracker(int(row["id"]))]
    else:
        results = probe_all(enabled_only=True)
    print(json.dumps([asdict(result) for result in results], indent=2))
    return 1 if any(result.status == "error" for result in results) else 0


def set_enabled(args: argparse.Namespace) -> int:
    row = _tracker(repository=args.repository, tracker_id=args.tracker_id)
    enabled = 1 if args.command == "resume" else 0
    with transaction() as conn:
        conn.execute(
            "UPDATE trackers SET enabled = ?, updated_at = ? WHERE id = ?",
            (enabled, utcnow(), row["id"]),
        )
    action = "resumed" if enabled else "paused"
    audit(None, f"cli_tracker_{action}", "tracker", row["id"], row["repository"])
    print(json.dumps({"ok": True, "action": action, "tracker_id": row["id"], "repository": row["repository"]}, indent=2))
    return 0


def set_refresh(args: argparse.Namespace) -> int:
    row = _tracker(repository=args.repository, tracker_id=args.tracker_id)
    hours = validate_refresh_hours(args.hours)
    with transaction() as conn:
        conn.execute(
            "UPDATE trackers SET refresh_hours = ?, updated_at = ? WHERE id = ?",
            (hours, utcnow(), row["id"]),
        )
    audit(None, "cli_tracker_refresh_changed", "tracker", row["id"], f"{hours}h")
    print(json.dumps({"ok": True, "action": "refresh_updated", "tracker_id": row["id"], "repository": row["repository"], "refresh_hours": hours}, indent=2))
    return 0


def set_tags(args: argparse.Namespace) -> int:
    row = _tracker(repository=args.repository, tracker_id=args.tracker_id)
    current = split_tags(row["tags"])
    requested = split_tags(normalise_tags(args.tags))
    if args.replace:
        updated = requested
    elif args.remove:
        remove_set = {tag.casefold() for tag in requested}
        updated = [tag for tag in current if tag.casefold() not in remove_set]
    else:
        updated = split_tags(normalise_tags([*current, *requested]))
    value = normalise_tags(updated)
    with transaction() as conn:
        conn.execute(
            "UPDATE trackers SET tags = ?, updated_at = ? WHERE id = ?",
            (value, utcnow(), row["id"]),
        )
    audit(None, "cli_tracker_tags_changed", "tracker", row["id"], value)
    print(json.dumps({"ok": True, "action": "tags_updated", "tracker_id": row["id"], "repository": row["repository"], "tags": split_tags(value)}, indent=2))
    return 0


def fleet(_: argparse.Namespace) -> int:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM trackers ORDER BY machine_name COLLATE NOCASE, name COLLATE NOCASE").fetchall()
    groups: dict[str, dict] = {}
    for row in rows:
        tracker = _row_dict(row)
        key = tracker.get("machine_name") or tracker.get("install_host") or "Unassigned"
        group = groups.setdefault(
            key,
            {
                "machine": key,
                "host": tracker.get("install_host"),
                "services": [],
                "online": 0,
                "offline": 0,
                "updates_available": 0,
                "needs_attention": 0,
            },
        )
        group["services"].append(tracker)
        if tracker.get("last_probe_status") == "ok":
            group["online"] += 1
        elif tracker.get("last_probe_status") == "error":
            group["offline"] += 1
        if tracker["update_available"]:
            group["updates_available"] += 1
        if tracker["needs_attention"]:
            group["needs_attention"] += 1
    print(json.dumps({"ok": True, "machines": list(groups.values())}, indent=2))
    return 0


def analyse(args: argparse.Namespace) -> int:
    result = analyse_tracker(tracker_id=args.tracker_id, repository=args.repository)
    print(json.dumps({"ok": True, **asdict(result)}, indent=2))
    return 0


def ask(args: argparse.Namespace) -> int:
    result = ask_tracker(
        args.question,
        tracker_id=args.tracker_id,
        repository=args.repository,
    )
    print(json.dumps({"ok": True, **asdict(result)}, indent=2))
    return 0


def notification_smoke(args: argparse.Namespace) -> int:
    init_db()
    if args.send and not args.confirm:
        raise ValueError("Use --confirm to send the deterministic notification smoke test.")
    result = notification_smoke_test(send=bool(args.send))
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


def portainer_status(_: argparse.Namespace) -> int:
    result = portainer_test_connection()
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


def portainer_inventory_command(_: argparse.Namespace) -> int:
    init_db()
    print(json.dumps({"ok": True, **inventory_summary()}, indent=2))
    return 0


def portainer_sync_command(args: argparse.Namespace) -> int:
    init_db()
    if args.due:
        last = parse_utc(get_setting("portainer_last_sync_at", ""))
        hours = int(get_setting("portainer_sync_hours", "1") or 1)
        if last is not None:
            from datetime import datetime, timezone
            if (datetime.now(timezone.utc) - last).total_seconds() < hours * 3600:
                print(json.dumps({"ok": True, "action": "skipped", "reason": "not_due", "last_sync_at": last.isoformat(), "sync_hours": hours}, indent=2))
                return 0
    result = sync_inventory()
    print(json.dumps({"ok": result.ok, "action": "synchronised", **asdict(result)}, indent=2))
    return 0 if result.ok else 1


def portainer_import_command(args: argparse.Namespace) -> int:
    tracker_id, action = import_service(
        args.service_id, args.repository, name=args.name,
        refresh_hours=validate_refresh_hours(args.refresh_hours),
        tags=normalise_tags(args.tags),
        include_prereleases=bool(args.include_prereleases),
    )
    check_result = check_tracker(tracker_id, baseline=action == "added")
    print(json.dumps({
        "ok": check_result.status == "ok", "action": action,
        "tracker_id": tracker_id, "check": asdict(check_result),
    }, indent=2))
    return 0 if check_result.status == "ok" else 2


def upgrades(_: argparse.Namespace) -> int:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.*, d.id AS decision_id, d.decision_status, d.priority AS decision_priority,
                   d.risk AS decision_risk, d.maintenance_date, d.checklist_json,
                   d.rollback_notes, d.change_record_url, d.decision_notes,
                   d.previous_version, d.deployed_version, d.deployed_at
              FROM trackers t
              LEFT JOIN upgrade_decisions d
                ON d.tracker_id = t.id
               AND d.release_version = COALESCE(NULLIF(t.current_version, ''), t.current_release_name)
             ORDER BY t.name COLLATE NOCASE
            """
        ).fetchall()
    items = []
    attention_items = []
    for row in rows:
        item = _row_dict(row)
        if item["needs_attention"]:
            attention_items.append({
                "id": item["id"],
                "name": item["name"],
                "repository": item["repository"],
                "machine_name": item.get("machine_name"),
                "install_host": item.get("install_host"),
                "effective_installed_version": item.get("effective_installed_version"),
                "current_version": item.get("current_version"),
                "attention": item["attention"],
            })
        if not item["update_available"]:
            continue
        item["decision_status"] = item.get("decision_status") or "review"
        item["priority"] = item.get("decision_priority") or "normal"
        item["risk"] = item.get("decision_risk") or "unknown"
        item["checklist"] = load_checklist(item.get("checklist_json"))
        item["checklist_summary"] = checklist_summary(item["checklist"])
        items.append(item)
    decision_rank = {"update": 0, "review": 1, "wait": 2, "ignore": 3, "deployed": 4}
    priority_rank = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    items.sort(key=lambda item: (decision_rank.get(item["decision_status"], 9), priority_rank.get(item["priority"], 9), item.get("maintenance_date") or "9999-12-31", item["name"].casefold()))
    attention_items.sort(key=lambda item: item["name"].casefold())
    print(json.dumps({
        "ok": True,
        "count": len(items),
        "updates_available": len(items),
        "needs_attention_count": len(attention_items),
        "upgrades": items,
        "needs_attention": attention_items,
    }, indent=2))
    return 0


def decide_upgrade(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise ValueError("Use --confirm after the user approves changing this upgrade decision.")
    row = _tracker(repository=args.repository, tracker_id=args.tracker_id)
    tracker = dict(row)
    target_release = release_key(tracker)
    if not target_release:
        raise ValueError("Check this tracker upstream before creating an upgrade decision.")
    with connect() as conn:
        existing_row = conn.execute(
            "SELECT * FROM upgrade_decisions WHERE tracker_id = ? AND release_version = ?",
            (tracker["id"], target_release),
        ).fetchone()
    existing = dict(existing_row) if existing_row else {}
    if existing.get("decision_status") == "deployed":
        raise ValueError("A deployed release record is immutable.")
    status_value = validate_choice(args.decision, DECISION_VALUES - {"deployed"}, "Decision")
    priority_value = validate_choice(args.priority or existing.get("priority") or "normal", PRIORITY_VALUES, "Priority")
    risk_value = validate_choice(args.risk or existing.get("risk") or "unknown", RISK_VALUES, "Risk")
    maintenance_value = validate_maintenance_date(args.maintenance_date if args.maintenance_date is not None else existing.get("maintenance_date"))
    change_record_value = validate_change_record_url(args.change_record_url if args.change_record_url is not None else existing.get("change_record_url"))
    if args.checklist_item is None:
        checklist = load_checklist(existing.get("checklist_json"))
    else:
        done = set(args.checklist_done or [])
        checklist = []
        for index, text in enumerate(args.checklist_item[:30]):
            text = str(text).strip()
            if not text:
                continue
            if len(text) > 240:
                raise ValueError("Checklist items must be 240 characters or fewer.")
            checklist.append({"text": text, "done": index in done})
    installed = tracker.get("detected_installed_version") or tracker.get("installed_version")
    now = utcnow()
    installed_at_decision = existing.get("installed_version_at_decision") or installed
    values = (
        tracker.get("current_release_name") or target_release, installed_at_decision, status_value,
        priority_value, risk_value, maintenance_value, checklist_json(checklist),
        args.rollback_notes if args.rollback_notes is not None else existing.get("rollback_notes"),
        change_record_value, args.notes if args.notes is not None else existing.get("decision_notes"),
        now, None,
    )
    with transaction() as conn:
        if existing:
            conn.execute(
                """UPDATE upgrade_decisions SET release_name=?, installed_version_at_decision=?,
                   decision_status=?, priority=?, risk=?, maintenance_date=?, checklist_json=?,
                   rollback_notes=?, change_record_url=?, decision_notes=?, updated_at=?, updated_by=?
                   WHERE id=?""",
                (*values, existing["id"]),
            )
            decision_id = int(existing["id"])
        else:
            cursor = conn.execute(
                """INSERT INTO upgrade_decisions
                   (tracker_id, release_version, release_name, installed_version_at_decision,
                    decision_status, priority, risk, maintenance_date, checklist_json,
                    rollback_notes, change_record_url, decision_notes, created_at, updated_at, updated_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (tracker["id"], target_release, *values[:10], now, now, None),
            )
            decision_id = int(cursor.lastrowid)
    audit(None, "cli_upgrade_decision_saved", "upgrade_decision", decision_id, f"{tracker['name']} {target_release}: {status_value}")
    print(json.dumps({
        "ok": True, "action": "decision_saved", "decision_id": decision_id,
        "tracker_id": int(tracker["id"]), "name": tracker["name"],
        "release_version": target_release, "decision_status": status_value,
        "priority": priority_value, "risk": risk_value,
        "maintenance_date": maintenance_value, "checklist_summary": checklist_summary(checklist),
    }, indent=2))
    return 0


def mark_upgrade_deployed(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise ValueError("Use --confirm only after the user confirms that this release was deployed.")
    row = _tracker(repository=args.repository, tracker_id=args.tracker_id)
    tracker = dict(row)
    target_release = release_key(tracker)
    if not target_release:
        raise ValueError("Check this tracker upstream before recording a deployment.")
    installed = tracker.get("detected_installed_version") or tracker.get("installed_version")
    now = utcnow()
    with transaction() as conn:
        existing = conn.execute(
            "SELECT * FROM upgrade_decisions WHERE tracker_id = ? AND release_version = ?",
            (tracker["id"], target_release),
        ).fetchone()
        if existing and existing["decision_status"] == "deployed":
            previous_version = existing["previous_version"] or existing["installed_version_at_decision"] or installed
            decision_id = int(existing["id"])
        elif existing:
            previous_version = existing["installed_version_at_decision"] or installed
            conn.execute(
                """UPDATE upgrade_decisions SET decision_status='deployed', previous_version=?,
                   deployed_version=?, deployed_at=?, updated_at=?, updated_by=NULL WHERE id=?""",
                (previous_version, target_release, now, now, existing["id"]),
            )
            decision_id = int(existing["id"])
        else:
            previous_version = installed
            cursor = conn.execute(
                """INSERT INTO upgrade_decisions
                   (tracker_id, release_version, release_name, installed_version_at_decision,
                    decision_status, priority, risk, maintenance_date, checklist_json, rollback_notes,
                    change_record_url, decision_notes, previous_version, deployed_version, deployed_at,
                    created_at, updated_at, updated_by)
                   VALUES (?, ?, ?, ?, 'deployed', 'normal', 'unknown', NULL, '[]', NULL, NULL, ?, ?, ?, ?, ?, ?, NULL)""",
                (tracker["id"], target_release, tracker.get("current_release_name") or target_release, installed, args.notes, previous_version, target_release, now, now, now),
            )
            decision_id = int(cursor.lastrowid)
    audit(None, "cli_upgrade_deployed", "upgrade_decision", decision_id, f"{tracker['name']} {target_release}")
    print(json.dumps({
        "ok": True, "action": "deployed", "decision_id": decision_id,
        "tracker_id": int(tracker["id"]), "name": tracker["name"],
        "previous_version": previous_version, "deployed_version": target_release, "deployed_at": now,
    }, indent=2))
    return 0


def remove(args: argparse.Namespace) -> int:
    row = _tracker(repository=args.repository, tracker_id=args.tracker_id)
    with transaction() as conn:
        conn.execute("DELETE FROM trackers WHERE id = ?", (row["id"],))
    audit(None, "cli_tracker_removed", "tracker", row["id"], row["repository"])
    print(json.dumps({"ok": True, "action": "removed", "name": row["name"], "repository": row["repository"]}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Software Release Radar trackers.")
    sub = parser.add_subparsers(dest="command", required=True)

    status_parser = sub.add_parser("status", help="Show dashboard health and summary counts")
    status_parser.set_defaults(func=status)
    list_parser = sub.add_parser("list", help="List all trackers")
    list_parser.set_defaults(func=list_trackers)
    fleet_parser = sub.add_parser("fleet", help="Show trackers grouped by machine")
    fleet_parser.set_defaults(func=fleet)
    upgrades_parser = sub.add_parser("upgrades", help="Show the managed upgrade decision queue")
    upgrades_parser.set_defaults(func=upgrades)

    notification_smoke_parser = sub.add_parser("notification-smoke-test", help="Validate deterministic notification delivery without an LLM")
    notification_smoke_parser.add_argument("--send", action="store_true", help="Send the fixed smoke-test message to enabled notification recipients")
    notification_smoke_parser.add_argument("--confirm", action="store_true", help="Confirm external notification delivery")
    notification_smoke_parser.set_defaults(func=notification_smoke)

    show_parser = sub.add_parser("show", help="Show one tracker and recent events")
    _target_args(show_parser)
    show_parser.set_defaults(func=show)

    track_parser = sub.add_parser("track", help="Add or idempotently update a tracker")
    track_parser.add_argument("--repository", required=True)
    track_parser.add_argument("--name")
    track_parser.add_argument("--strategy", choices=("release", "tag"))
    group = track_parser.add_mutually_exclusive_group()
    group.add_argument("--include-prereleases", dest="include_prereleases", action="store_true", default=None)
    group.add_argument("--stable-only", dest="include_prereleases", action="store_false")
    track_parser.add_argument("--refresh-hours", type=int)
    track_parser.add_argument("--tags", default="")
    track_parser.add_argument("--replace-tags", action="store_true")
    track_parser.add_argument("--homepage-url")
    track_parser.add_argument("--notes")
    track_parser.add_argument("--installed-version")
    track_parser.add_argument("--machine-name")
    track_parser.add_argument("--host")
    track_parser.add_argument("--port", type=int)
    track_parser.add_argument("--scheme", choices=("http", "https", "tcp"))
    track_parser.add_argument("--probe-mode", choices=("manual", "http_auto", "http_json", "http_regex", "ssh_docker", "portainer"))
    track_parser.add_argument("--container")
    track_parser.add_argument("--ssh-user")
    track_parser.add_argument("--ssh-key-name")
    track_parser.set_defaults(func=track)

    check_parser = sub.add_parser("check", help="Check upstream releases")
    target = check_parser.add_mutually_exclusive_group()
    target.add_argument("--repository")
    target.add_argument("--tracker-id", type=int)
    check_parser.add_argument("--due", action="store_true")
    check_parser.set_defaults(func=check)

    probe_parser = sub.add_parser("probe", help="Probe installed services and versions")
    target = probe_parser.add_mutually_exclusive_group()
    target.add_argument("--repository")
    target.add_argument("--tracker-id", type=int)
    probe_parser.set_defaults(func=probe)

    for name in ("pause", "resume"):
        state_parser = sub.add_parser(name, help=f"{name.title()} one tracker")
        _target_args(state_parser)
        state_parser.set_defaults(func=set_enabled)

    refresh_parser = sub.add_parser("refresh", help="Change one tracker refresh interval")
    _target_args(refresh_parser)
    refresh_parser.add_argument("--hours", type=int, required=True)
    refresh_parser.set_defaults(func=set_refresh)

    tags_parser = sub.add_parser("tags", help="Add, replace, or remove tracker tags")
    _target_args(tags_parser)
    tags_parser.add_argument("--tags", required=True)
    mode = tags_parser.add_mutually_exclusive_group()
    mode.add_argument("--replace", action="store_true")
    mode.add_argument("--remove", action="store_true")
    tags_parser.set_defaults(func=set_tags)

    analyse_parser = sub.add_parser("analyse", help="Run an explicit LiteLLM release comparison")
    _target_args(analyse_parser)
    analyse_parser.set_defaults(func=analyse)

    ask_parser = sub.add_parser("ask", help="Ask the configured dashboard assistant about one tracker")
    _target_args(ask_parser)
    ask_parser.add_argument("--question", required=True)
    ask_parser.set_defaults(func=ask)

    portainer_status_parser = sub.add_parser("portainer-status", help="Test the configured Portainer connection")
    portainer_status_parser.set_defaults(func=portainer_status)

    portainer_inventory_parser = sub.add_parser("portainer-inventory", help="List discovered Portainer environments and containers")
    portainer_inventory_parser.set_defaults(func=portainer_inventory_command)

    portainer_sync_parser = sub.add_parser("portainer-sync", help="Synchronise Docker inventory from Portainer")
    portainer_sync_parser.add_argument("--due", action="store_true", help="Synchronise only when the configured interval is due")
    portainer_sync_parser.set_defaults(func=portainer_sync_command)

    portainer_import_parser = sub.add_parser("portainer-import", help="Import or update a tracker from a Portainer container")
    portainer_import_parser.add_argument("--service-id", type=int, required=True)
    portainer_import_parser.add_argument("--repository", required=True)
    portainer_import_parser.add_argument("--name")
    portainer_import_parser.add_argument("--refresh-hours", type=int, default=6)
    portainer_import_parser.add_argument("--tags", default="portainer,docker")
    portainer_import_parser.add_argument("--include-prereleases", action="store_true")
    portainer_import_parser.set_defaults(func=portainer_import_command)

    decide_parser = sub.add_parser("decide", help="Save a managed upgrade decision")
    _target_args(decide_parser)
    decide_parser.add_argument("--decision", required=True, choices=("review", "update", "wait", "ignore"))
    decide_parser.add_argument("--priority", choices=("low", "normal", "high", "urgent"))
    decide_parser.add_argument("--risk", choices=("unknown", "low", "medium", "high", "critical"))
    decide_parser.add_argument("--maintenance-date")
    decide_parser.add_argument("--checklist-item", action="append")
    decide_parser.add_argument("--checklist-done", type=int, action="append")
    decide_parser.add_argument("--rollback-notes")
    decide_parser.add_argument("--change-record-url")
    decide_parser.add_argument("--notes")
    decide_parser.add_argument("--confirm", action="store_true")
    decide_parser.set_defaults(func=decide_upgrade)

    deployed_parser = sub.add_parser("deployed", help="Record the current release as deployed")
    _target_args(deployed_parser)
    deployed_parser.add_argument("--notes")
    deployed_parser.add_argument("--confirm", action="store_true")
    deployed_parser.set_defaults(func=mark_upgrade_deployed)

    remove_parser = sub.add_parser("remove", help="Permanently remove one tracker")
    _target_args(remove_parser)
    remove_parser.set_defaults(func=remove)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
