from __future__ import annotations

from typing import Any

from .db import connect, transaction, utcnow

ACTIVE = ("queued", "running")


def enqueue_sync(requested_by: int | None = None) -> tuple[int, bool]:
    with transaction() as conn:
        active = conn.execute(
            "SELECT id FROM portainer_sync_jobs WHERE status IN ('queued','running') ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if active:
            return int(active["id"]), False
        cur = conn.execute(
            "INSERT INTO portainer_sync_jobs(status,requested_by,requested_at,message) VALUES('queued',?,?,?)",
            (requested_by, utcnow(), "Waiting for worker"),
        )
        return int(cur.lastrowid), True


def latest_job() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM portainer_sync_jobs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def claim_job(worker_id: str) -> dict[str, Any] | None:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM portainer_sync_jobs WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
        if not row:
            return None
        changed = conn.execute(
            "UPDATE portainer_sync_jobs SET status='running',started_at=?,worker_id=?,message='Starting synchronisation' WHERE id=? AND status='queued'",
            (utcnow(), worker_id, row["id"]),
        )
        if changed.rowcount != 1:
            return None
        return dict(conn.execute("SELECT * FROM portainer_sync_jobs WHERE id=?", (row["id"],)).fetchone())


def update_job(job_id: int, **fields: Any) -> None:
    allowed = {"total_environments","processed_environments","services_found","offline_environments","unexpected_errors","current_environment","message","error"}
    values = {k:v for k,v in fields.items() if k in allowed}
    if not values:
        return
    with transaction() as conn:
        conn.execute("UPDATE portainer_sync_jobs SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?", [*values.values(), job_id])


def finish_job(job_id: int, *, success: bool, message: str, error: str | None = None) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE portainer_sync_jobs SET status=?,completed_at=?,current_environment=NULL,message=?,error=? WHERE id=?",
            ("completed" if success else "failed", utcnow(), message, error, job_id),
        )


def enqueue_import(payload: dict[str, Any], requested_by: int | None = None) -> tuple[int, bool]:
    import json
    with transaction() as conn:
        active = conn.execute(
            "SELECT id FROM portainer_import_jobs WHERE status IN ('queued','running') ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if active:
            return int(active["id"]), False
        items = payload.get("items") or []
        cur = conn.execute(
            """INSERT INTO portainer_import_jobs
               (status,requested_by,requested_at,total_items,payload_json,message)
               VALUES('queued',?,?,?,?,?)""",
            (requested_by, utcnow(), len(items), json.dumps(payload), "Waiting for worker"),
        )
        return int(cur.lastrowid), True


def latest_import_job() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM portainer_import_jobs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def claim_import_job(worker_id: str) -> dict[str, Any] | None:
    with transaction() as conn:
        row = conn.execute(
            "SELECT * FROM portainer_import_jobs WHERE status='queued' ORDER BY id LIMIT 1"
        ).fetchone()
        if not row:
            return None
        changed = conn.execute(
            """UPDATE portainer_import_jobs
               SET status='running',started_at=?,worker_id=?,message='Preparing bulk import'
               WHERE id=? AND status='queued'""",
            (utcnow(), worker_id, row["id"]),
        )
        if changed.rowcount != 1:
            return None
        return dict(conn.execute(
            "SELECT * FROM portainer_import_jobs WHERE id=?", (row["id"],)
        ).fetchone())


def update_import_job(job_id: int, **fields: Any) -> None:
    allowed = {
        "total_items", "processed_items", "imported_items", "failed_items",
        "current_item", "message", "error",
    }
    values = {key: value for key, value in fields.items() if key in allowed}
    if not values:
        return
    with transaction() as conn:
        conn.execute(
            "UPDATE portainer_import_jobs SET "
            + ",".join(f"{key}=?" for key in values)
            + " WHERE id=?",
            [*values.values(), job_id],
        )


def finish_import_job(job_id: int, *, success: bool, message: str,
                      error: str | None = None) -> None:
    with transaction() as conn:
        conn.execute(
            """UPDATE portainer_import_jobs
               SET status=?,completed_at=?,current_item=NULL,message=?,error=?
               WHERE id=?""",
            ("completed" if success else "failed", utcnow(), message, error, job_id),
        )
