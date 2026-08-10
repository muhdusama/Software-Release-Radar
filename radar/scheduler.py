from __future__ import annotations

import json
import logging
import os
import signal
import time
from dataclasses import asdict

from .checker import check_all
from .db import init_db
from .notifications import dispatch_release_notifications

LOGGER = logging.getLogger("software_release_radar.scheduler")
_STOP = False


def _interval_seconds() -> int:
    raw = os.environ.get("RADAR_SCHEDULER_INTERVAL_SECONDS", "60").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("RADAR_SCHEDULER_INTERVAL_SECONDS must be an integer.") from exc
    if value < 30 or value > 3600:
        raise RuntimeError("RADAR_SCHEDULER_INTERVAL_SECONDS must be between 30 and 3600 seconds.")
    return value


def run_once() -> dict[str, object]:
    """Run due release checks once and dispatch notifications for new releases."""
    results = check_all(enabled_only=True, due_only=True)
    event_ids = [int(item.event_id) for item in results if item.event_id is not None]
    notifications = (
        dispatch_release_notifications(event_ids)
        if event_ids
        else {"sent": 0, "failed": 0, "skipped": 0}
    )
    summary = {
        "checked": len(results),
        "changed": sum(1 for item in results if item.changed),
        "errors": sum(1 for item in results if item.status == "error"),
        "notifications": notifications,
    }
    if os.environ.get("RADAR_SCHEDULER_LOG_RESULTS", "false").lower() == "true":
        summary["results"] = [asdict(item) for item in results]
    return summary


def _request_stop(_signum, _frame) -> None:
    global _STOP
    _STOP = True


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("RADAR_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    init_db()
    interval = _interval_seconds()
    LOGGER.info("Release scheduler started with a %s second polling interval.", interval)

    while not _STOP:
        started = time.monotonic()
        try:
            LOGGER.info("Scheduler cycle: %s", json.dumps(run_once(), sort_keys=True))
        except Exception:
            LOGGER.exception("Scheduler cycle failed.")

        remaining = max(0.0, interval - (time.monotonic() - started))
        deadline = time.monotonic() + remaining
        while not _STOP and time.monotonic() < deadline:
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))

    LOGGER.info("Release scheduler stopped.")


if __name__ == "__main__":
    main()
