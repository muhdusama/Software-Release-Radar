from __future__ import annotations

import json
import os
import socket
import time
import traceback

from .checker import check_tracker
from .db import init_db
from .portainer import import_services_batch, sync_inventory
from .portainer_jobs import (
    claim_import_job,
    claim_job,
    finish_import_job,
    finish_job,
    update_import_job,
    update_job,
)


def _run_sync(worker_id: str) -> bool:
    job = claim_job(worker_id)
    if not job:
        return False
    job_id = int(job["id"])
    try:
        def progress(**values):
            update_job(job_id, **values)
        result = sync_inventory(progress=progress)
        message = (
            f"Synchronised {result.environments} environments and "
            f"{result.services} containers; {result.offline_environments} offline."
        )
        finish_job(job_id, success=True, message=message)
    except Exception as exc:
        finish_job(
            job_id,
            success=False,
            message="Inventory synchronisation failed",
            error=f"{exc}\n{traceback.format_exc()[-3000:]}",
        )
    return True


def _run_import(worker_id: str) -> bool:
    job = claim_import_job(worker_id)
    if not job:
        return False
    job_id = int(job["id"])
    try:
        payload = json.loads(job["payload_json"])
        def progress(**values):
            update_import_job(job_id, **values)
        result = import_services_batch(
            payload.get("items") or [],
            refresh_hours=int(payload.get("refresh_hours") or 24),
            tags=str(payload.get("tags") or "portainer,docker"),
            include_prereleases=bool(payload.get("include_prereleases", False)),
            progress=progress,
        )
        baseline_failures: list[str] = []
        imported = result["imported"]
        for index, item in enumerate(imported, start=1):
            update_import_job(
                job_id,
                current_item=item["name"],
                message=f"Establishing release baseline {index} of {len(imported)}",
            )
            try:
                check_tracker(item["tracker_id"], baseline=item["action"] == "added")
            except Exception as exc:
                baseline_failures.append(f"{item['name']}: {exc}")
        failures = [*result["failures"], *baseline_failures]
        finish_import_job(
            job_id,
            success=True,
            message=(
                f"Imported or updated {len(imported)} tracker(s); "
                f"{len(failures)} item(s) need attention."
            ),
            error="\n".join(failures[:30]) or None,
        )
    except Exception as exc:
        finish_import_job(
            job_id,
            success=False,
            message="Inventory bulk import failed",
            error=f"{exc}\n{traceback.format_exc()[-3000:]}",
        )
    return True


def main() -> None:
    init_db()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    while True:
        if _run_sync(worker_id):
            time.sleep(1)
            continue
        if _run_import(worker_id):
            time.sleep(1)
            continue
        time.sleep(2)


if __name__ == "__main__":
    main()
