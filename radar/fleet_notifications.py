from __future__ import annotations

import hmac
import sqlite3
from typing import Any

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .db import audit, connect, get_setting, set_setting, transaction, utcnow
from .notifications import NOTIFICATION_MODES, ensure_notification_preferences
from .portainer_jobs import enqueue_sync
from .versioning import classify_tracker_state

MAX_DISPLAY_NAME = 120


def _columns(conn, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}


def ensure_fleet_notification_schema() -> None:
    """Install additive name override and notification preference storage."""
    ensure_notification_preferences()
    with transaction() as conn:
        additions = (
            ("trackers", "display_name_override", "TEXT"),
            ("portainer_environments", "display_name_override", "TEXT"),
            ("portainer_services", "stack_name_override", "TEXT"),
        )
        for table, column, definition in additions:
            if column in _columns(conn, table):
                continue
            try:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                )
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise


def _clean_display_name(
    value: str | None,
    *,
    label: str,
    allow_blank: bool = False,
) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        if allow_blank:
            return None
        raise ValueError(f"{label} is required.")
    if len(cleaned) > MAX_DISPLAY_NAME:
        raise ValueError(
            f"{label} must be {MAX_DISPLAY_NAME} characters or fewer."
        )
    if any(ord(character) < 32 for character in cleaned):
        raise ValueError(f"{label} contains unsupported control characters.")
    return cleaned


def _source_service_name(row) -> str:
    return str(
        row["portainer_service_name"]
        or row["portainer_container_name"]
        or row["name"]
        or "Unnamed software"
    ).strip()


def reconcile_portainer_names() -> int:
    """Apply current provider source names unless a local override is active."""
    ensure_fleet_notification_schema()
    changed = 0
    now = utcnow()
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.name, t.machine_name, t.display_name_override,
                   ps.service_name AS portainer_service_name,
                   ps.container_name AS portainer_container_name,
                   pe.name AS portainer_machine_name,
                   pe.display_name_override AS machine_name_override
              FROM trackers t
              JOIN portainer_services ps ON ps.id = t.portainer_service_id
              LEFT JOIN portainer_environments pe
                ON pe.endpoint_id = ps.endpoint_id
             WHERE t.inventory_source IN ('portainer','dockhand')
            """
        ).fetchall()
        for row in rows:
            source_name = _source_service_name(row)
            custom_name = str(row["display_name_override"] or "").strip()
            target_name = custom_name or source_name
            target_machine = str(
                row["machine_name_override"]
                or row["portainer_machine_name"]
                or row["machine_name"]
                or ""
            ).strip() or None
            if (
                str(row["name"] or "") != target_name
                or (row["machine_name"] or None) != target_machine
            ):
                conn.execute(
                    """
                    UPDATE trackers
                       SET name = ?, machine_name = ?, updated_at = ?
                     WHERE id = ?
                    """,
                    (target_name, target_machine, now, row["id"]),
                )
                changed += 1
    return changed


def _require_csrf() -> None:
    expected = str(session.get("csrf_token") or "")
    supplied = str(request.form.get("csrf_token") or "")
    if not expected or not hmac.compare_digest(expected, supplied):
        abort(400, "Invalid CSRF token")


def _require_login():
    if g.user is None:
        return redirect(url_for("login", next=request.path))
    return None


def _require_admin():
    response = _require_login()
    if response is not None:
        return response
    if str(g.user["role"]) != "admin":
        abort(403)
    return None


def _fleet_data() -> list[dict[str, Any]]:
    reconcile_portainer_names()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.*,
                   COALESCE(
                       t.detected_installed_version,
                       t.installed_version
                   ) AS effective_installed_version,
                   ps.id AS linked_service_id,
                   ps.endpoint_id AS portainer_endpoint_id,
                   ps.service_name AS portainer_service_name,
                   ps.container_name AS portainer_container_name,
                   ps.stack_name AS portainer_stack_name,
                   ps.stack_name_override,
                   pe.name AS portainer_machine_name,
                   pe.display_name_override AS machine_name_override,
                   pe.host AS portainer_host
              FROM trackers t
              LEFT JOIN portainer_services ps
                ON ps.id = t.portainer_service_id
              LEFT JOIN portainer_environments pe
                ON pe.endpoint_id = ps.endpoint_id
             ORDER BY COALESCE(
                          NULLIF(pe.display_name_override, ''),
                          NULLIF(pe.name, ''),
                          NULLIF(t.machine_name, ''),
                          NULLIF(t.install_host, ''),
                          'Unassigned'
                      ) COLLATE NOCASE,
                      t.name COLLATE NOCASE
            """
        ).fetchall()

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        tracker = dict(row)
        tracker.update(classify_tracker_state(tracker))

        source_display_name = str(
            tracker.get("portainer_service_name")
            or tracker.get("portainer_container_name")
            or tracker.get("name")
            or "Unnamed software"
        ).strip()
        custom_display_name = str(
            tracker.get("display_name_override") or ""
        ).strip()
        tracker["source_display_name"] = source_display_name
        tracker["display_name"] = custom_display_name or source_display_name
        tracker["has_display_name_override"] = bool(custom_display_name)

        source_stack_name = str(
            tracker.get("portainer_stack_name") or ""
        ).strip()
        custom_stack_name = str(
            tracker.get("stack_name_override") or ""
        ).strip()
        tracker["source_stack_name"] = source_stack_name
        tracker["effective_stack_name"] = (
            custom_stack_name or source_stack_name
        )
        tracker["has_stack_name_override"] = bool(custom_stack_name)

        endpoint_id = tracker.get("portainer_endpoint_id")
        source_machine_name = str(
            tracker.get("portainer_machine_name")
            or tracker.get("machine_name")
            or tracker.get("install_host")
            or "Unassigned"
        ).strip()
        custom_machine_name = str(
            tracker.get("machine_name_override") or ""
        ).strip()
        effective_machine_name = (
            custom_machine_name or source_machine_name or "Unassigned"
        )
        host = tracker.get("portainer_host") or tracker.get("install_host")
        group_key = (
            f"portainer:{int(endpoint_id)}"
            if endpoint_id not in (None, "")
            else f"manual:{effective_machine_name.casefold()}:{host or ''}"
        )
        machine = grouped.setdefault(
            group_key,
            {
                "name": effective_machine_name,
                "source_name": source_machine_name,
                "has_name_override": bool(custom_machine_name),
                "host": host,
                "endpoint_id": (
                    int(endpoint_id)
                    if endpoint_id not in (None, "")
                    else None
                ),
                "trackers": [],
                "online": 0,
                "offline": 0,
                "updates": 0,
                "needs_attention": 0,
            },
        )
        machine["trackers"].append(tracker)
        if tracker.get("last_probe_status") == "ok":
            machine["online"] += 1
        elif tracker.get("last_probe_status") == "error":
            machine["offline"] += 1
        if tracker["update_available"]:
            machine["updates"] += 1
        if tracker["needs_attention"]:
            machine["needs_attention"] += 1

    machines = list(grouped.values())
    for machine in machines:
        machine["trackers"].sort(
            key=lambda item: str(item["display_name"]).casefold()
        )
    machines.sort(key=lambda item: str(item["name"]).casefold())
    return machines


def _notification_trackers(user_id: int) -> list[dict[str, Any]]:
    reconcile_portainer_names()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.name, t.repository, t.enabled, t.machine_name,
                   t.install_host, t.current_version,
                   COALESCE(p.mode, 'inherit') AS notification_mode
              FROM trackers t
              LEFT JOIN tracker_notification_preferences p
                ON p.tracker_id = t.id AND p.user_id = ?
             ORDER BY t.name COLLATE NOCASE
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _upsert_notification_mode(
    conn,
    *,
    user_id: int,
    tracker_id: int,
    mode: str,
) -> None:
    if mode not in NOTIFICATION_MODES:
        raise ValueError("Invalid software notification preference.")
    if mode == "inherit":
        conn.execute(
            """
            DELETE FROM tracker_notification_preferences
             WHERE user_id = ? AND tracker_id = ?
            """,
            (user_id, tracker_id),
        )
        return
    conn.execute(
        """
        INSERT INTO tracker_notification_preferences
            (user_id, tracker_id, mode, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, tracker_id) DO UPDATE SET
            mode = excluded.mode,
            updated_at = excluded.updated_at
        """,
        (user_id, tracker_id, mode, utcnow()),
    )


def install_fleet_notification_controls(app: Flask) -> None:
    """Install editable Fleet names and granular release notification controls."""
    ensure_fleet_notification_schema()

    def fleet_view():
        response = _require_login()
        if response is not None:
            return response
        return render_template(
            "fleet.html",
            machines=_fleet_data(),
            portainer_enabled=(
                str(get_setting("portainer_enabled", "0")) == "1"
            ),
            provider_label=str(
                get_setting("inventory_provider", "portainer") or "portainer"
            ).title(),
        )

    app.view_functions["fleet"] = fleet_view

    @app.post("/fleet/machines/<int:endpoint_id>/name")
    def fleet_machine_name(endpoint_id: int):
        response = _require_admin()
        if response is not None:
            return response
        _require_csrf()
        action = request.form.get("action", "save")
        try:
            with transaction() as conn:
                environment = conn.execute(
                    """
                    SELECT endpoint_id, name, display_name_override
                      FROM portainer_environments
                     WHERE endpoint_id = ?
                    """,
                    (endpoint_id,),
                ).fetchone()
                if environment is None:
                    abort(404)
                if action == "source":
                    override = None
                elif action == "save":
                    override = _clean_display_name(
                        request.form.get("display_name"),
                        label="Machine display name",
                        allow_blank=True,
                    )
                    if override == str(environment["name"] or "").strip():
                        override = None
                else:
                    raise ValueError("Invalid machine-name action.")
                effective_name = override or str(
                    environment["name"] or f"Environment {endpoint_id}"
                )
                conn.execute(
                    """
                    UPDATE portainer_environments
                       SET display_name_override = ?, updated_at = ?
                     WHERE endpoint_id = ?
                    """,
                    (override, utcnow(), endpoint_id),
                )
                conn.execute(
                    """
                    UPDATE trackers
                       SET machine_name = ?, updated_at = ?
                     WHERE portainer_service_id IN (
                         SELECT id FROM portainer_services
                          WHERE endpoint_id = ?
                     )
                    """,
                    (effective_name, utcnow(), endpoint_id),
                )
            audit(
                int(g.user["id"]),
                "fleet_machine_name_updated",
                "portainer_environment",
                endpoint_id,
                effective_name,
            )
            flash(
                (
                    "Machine name now follows the inventory provider."
                    if override is None
                    else f"Machine display name changed to {override}."
                ),
                "success",
            )
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("fleet"), code=303)

    @app.post("/fleet/trackers/<int:tracker_id>/names")
    def fleet_tracker_names(tracker_id: int):
        response = _require_admin()
        if response is not None:
            return response
        _require_csrf()
        action = request.form.get("action", "save")
        try:
            with transaction() as conn:
                row = conn.execute(
                    """
                    SELECT t.id, t.name, t.inventory_source,
                           t.display_name_override, t.machine_name,
                           ps.id AS service_id,
                           ps.service_name AS portainer_service_name,
                           ps.container_name AS portainer_container_name,
                           ps.stack_name AS portainer_stack_name
                      FROM trackers t
                      LEFT JOIN portainer_services ps
                        ON ps.id = t.portainer_service_id
                     WHERE t.id = ?
                    """,
                    (tracker_id,),
                ).fetchone()
                if row is None:
                    abort(404)

                source_name = _source_service_name(row)
                if action in {"source", "source_all"}:
                    display_override = None
                elif action in {"save", "source_stack"}:
                    display_override = _clean_display_name(
                        request.form.get("display_name"),
                        label="Software display name",
                        allow_blank=True,
                    )
                    if display_override == source_name:
                        display_override = None
                else:
                    raise ValueError("Invalid software-name action.")
                effective_name = display_override or source_name

                service_id = row["service_id"]
                stack_override = None
                if service_id not in (None, ""):
                    source_stack = str(
                        row["portainer_stack_name"] or ""
                    ).strip()
                    if action in {"source_stack", "source_all"}:
                        stack_override = None
                    else:
                        stack_override = _clean_display_name(
                            request.form.get("stack_name"),
                            label="Stack or folder display name",
                            allow_blank=True,
                        )
                        if stack_override == source_stack:
                            stack_override = None
                    conn.execute(
                        """
                        UPDATE portainer_services
                           SET stack_name_override = ?, updated_at = ?
                         WHERE id = ?
                        """,
                        (stack_override, utcnow(), service_id),
                    )

                machine_name = row["machine_name"]
                if service_id in (None, "") and "machine_name" in request.form:
                    machine_name = _clean_display_name(
                        request.form.get("machine_name"),
                        label="Machine display name",
                        allow_blank=True,
                    )

                conn.execute(
                    """
                    UPDATE trackers
                       SET name = ?, display_name_override = ?,
                           machine_name = ?, updated_at = ?
                     WHERE id = ?
                    """,
                    (
                        effective_name,
                        display_override,
                        machine_name,
                        utcnow(),
                        tracker_id,
                    ),
                )
            audit(
                int(g.user["id"]),
                "fleet_software_name_updated",
                "tracker",
                tracker_id,
                effective_name,
            )
            flash(
                (
                    "Software name now follows the inventory provider."
                    if display_override is None
                    and row["inventory_source"] in {"portainer", "dockhand"}
                    else f"Display names updated for {effective_name}."
                ),
                "success",
            )
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("fleet"), code=303)

    @app.post("/fleet/sync-portainer-names")
    def fleet_sync_portainer_names():
        response = _require_admin()
        if response is not None:
            return response
        _require_csrf()
        job_id, created = enqueue_sync(int(g.user["id"]))
        message = (
            "Inventory name synchronisation queued. "
            "Source-managed Fleet names will refresh when the job completes."
            if created
            else "An inventory synchronisation is already queued or running."
        )
        flash(message, "success" if created else "info")
        audit(
            int(g.user["id"]),
            "fleet_name_sync_queued",
            "portainer_sync_job",
            job_id,
            message,
        )
        return redirect(url_for("portainer_inventory"), code=303)

    @app.route("/notifications", methods=["GET", "POST"])
    def notifications_preferences():
        response = _require_login()
        if response is not None:
            return response
        ensure_fleet_notification_schema()
        user_id = int(g.user["id"])

        if request.method == "POST":
            _require_csrf()
            action = request.form.get("action", "save_defaults")
            try:
                if action == "save_defaults":
                    with transaction() as conn:
                        conn.execute(
                            """
                            UPDATE users
                               SET notifications_enabled = ?,
                                   notify_email = ?,
                                   notify_pushover = ?,
                                   updated_at = ?
                             WHERE id = ?
                            """,
                            (
                                1
                                if request.form.get(
                                    "notifications_enabled"
                                )
                                else 0,
                                1 if request.form.get("notify_email") else 0,
                                1
                                if request.form.get("notify_pushover")
                                else 0,
                                utcnow(),
                                user_id,
                            ),
                        )
                    if (
                        str(g.user["role"]) == "admin"
                        and request.form.get("system_control_present")
                    ):
                        set_setting(
                            "notifications_enabled",
                            (
                                "1"
                                if request.form.get(
                                    "system_notifications_enabled"
                                )
                                else "0"
                            ),
                        )
                    audit(
                        user_id,
                        "notification_defaults_updated",
                        "user",
                        user_id,
                    )
                    flash("Notification defaults saved.", "success")
                elif action == "save_software":
                    modes: dict[int, str] = {}
                    for key, value in request.form.items():
                        if not key.startswith("mode_"):
                            continue
                        raw_id = key.removeprefix("mode_")
                        if not raw_id.isdigit():
                            continue
                        mode = str(value)
                        if mode not in NOTIFICATION_MODES:
                            raise ValueError(
                                "Invalid software notification preference."
                            )
                        modes[int(raw_id)] = mode
                    with transaction() as conn:
                        existing_ids = {
                            int(row["id"])
                            for row in conn.execute(
                                "SELECT id FROM trackers"
                            ).fetchall()
                        }
                        for tracker_id, mode in modes.items():
                            if tracker_id not in existing_ids:
                                continue
                            _upsert_notification_mode(
                                conn,
                                user_id=user_id,
                                tracker_id=tracker_id,
                                mode=mode,
                            )
                    audit(
                        user_id,
                        "software_notification_preferences_updated",
                        "user",
                        user_id,
                        f"{len(modes)} software preferences",
                    )
                    flash(
                        f"Saved notification preferences for {len(modes)} "
                        "software tracker(s).",
                        "success",
                    )
                elif action == "bulk_software":
                    mode = str(request.form.get("bulk_mode") or "")
                    if mode not in NOTIFICATION_MODES:
                        raise ValueError(
                            "Choose a valid bulk notification preference."
                        )
                    tracker_ids = sorted(
                        {
                            int(value)
                            for value in request.form.getlist("tracker_ids")
                            if str(value).isdigit()
                        }
                    )
                    if not tracker_ids:
                        raise ValueError("Select at least one software tracker.")
                    with transaction() as conn:
                        placeholders = ",".join("?" for _ in tracker_ids)
                        existing_ids = {
                            int(row["id"])
                            for row in conn.execute(
                                f"""
                                SELECT id FROM trackers
                                 WHERE id IN ({placeholders})
                                """,
                                tracker_ids,
                            ).fetchall()
                        }
                        for tracker_id in tracker_ids:
                            if tracker_id not in existing_ids:
                                continue
                            _upsert_notification_mode(
                                conn,
                                user_id=user_id,
                                tracker_id=tracker_id,
                                mode=mode,
                            )
                    audit(
                        user_id,
                        "software_notification_preferences_bulk_updated",
                        "user",
                        user_id,
                        f"{mode}: {','.join(map(str, tracker_ids))}",
                    )
                    flash(
                        f"Updated {len(existing_ids)} software notification "
                        "preference(s).",
                        "success",
                    )
                else:
                    raise ValueError("Unknown notification action.")
            except ValueError as exc:
                flash(str(exc), "error")
            return redirect(url_for("notifications_preferences"), code=303)

        with connect() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if user is None:
            session.clear()
            return redirect(url_for("login"))

        trackers = _notification_trackers(user_id)
        system_enabled = (
            str(get_setting("notifications_enabled", "1")) == "1"
        )
        default_enabled = bool(int(user["notifications_enabled"] or 0))
        counts = {"inherit": 0, "on": 0, "off": 0}
        for tracker in trackers:
            mode = str(tracker["notification_mode"])
            counts[mode] += 1
            if not system_enabled:
                tracker["effective_notification_state"] = "paused"
            elif mode == "on":
                tracker["effective_notification_state"] = "on"
            elif mode == "off":
                tracker["effective_notification_state"] = "off"
            else:
                tracker["effective_notification_state"] = (
                    "on" if default_enabled else "off"
                )

        return render_template(
            "notifications.html",
            notification_user=dict(user),
            has_pushover_key=bool(user["pushover_user_key_enc"]),
            trackers=trackers,
            system_enabled=system_enabled,
            preference_counts=counts,
            notification_modes=(
                ("inherit", "Use global default"),
                ("on", "Always notify"),
                ("off", "Mute"),
            ),
        )

    @app.after_request
    def preserve_full_editor_name_override(response):
        if (
            request.endpoint == "edit_tracker"
            and request.method == "POST"
            and response.status_code in {301, 302, 303}
            and request.view_args
            and str(request.form.get("name") or "").strip()
        ):
            tracker_id = int(request.view_args["tracker_id"])
            submitted_name = str(request.form["name"]).strip()
            with transaction() as conn:
                row = conn.execute(
                    """
                    SELECT t.inventory_source,
                           ps.service_name AS portainer_service_name,
                           ps.container_name AS portainer_container_name
                      FROM trackers t
                      LEFT JOIN portainer_services ps
                        ON ps.id = t.portainer_service_id
                     WHERE t.id = ?
                    """,
                    (tracker_id,),
                ).fetchone()
                if row and row["inventory_source"] in {"portainer", "dockhand"}:
                    source_name = _source_service_name(
                        {
                            "portainer_service_name": row[
                                "portainer_service_name"
                            ],
                            "portainer_container_name": row[
                                "portainer_container_name"
                            ],
                            "name": submitted_name,
                        }
                    )
                    override = (
                        None
                        if submitted_name == source_name
                        else submitted_name
                    )
                    conn.execute(
                        """
                        UPDATE trackers
                           SET display_name_override = ?, updated_at = ?
                         WHERE id = ?
                        """,
                        (override, utcnow(), tracker_id),
                    )
        return response
