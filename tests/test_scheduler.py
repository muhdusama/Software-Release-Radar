from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from radar import scheduler


class SchedulerTests(unittest.TestCase):
    def test_run_once_checks_due_trackers_and_notifies_new_releases(self):
        results = [
            SimpleNamespace(event_id=42, changed=True, status="ok"),
            SimpleNamespace(event_id=None, changed=False, status="ok"),
            SimpleNamespace(event_id=None, changed=False, status="error"),
        ]
        with patch("radar.scheduler.check_all", return_value=results) as check_all, patch(
            "radar.scheduler.dispatch_release_notifications",
            return_value={"sent": 2, "failed": 0, "skipped": 0},
        ) as dispatch:
            summary = scheduler.run_once()

        check_all.assert_called_once_with(enabled_only=True, due_only=True)
        dispatch.assert_called_once_with([42])
        self.assertEqual(summary["checked"], 3)
        self.assertEqual(summary["changed"], 1)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["notifications"]["sent"], 2)

    def test_run_once_does_not_dispatch_when_nothing_changed(self):
        results = [SimpleNamespace(event_id=None, changed=False, status="ok")]
        with patch("radar.scheduler.check_all", return_value=results), patch(
            "radar.scheduler.dispatch_release_notifications"
        ) as dispatch:
            summary = scheduler.run_once()

        dispatch.assert_not_called()
        self.assertEqual(summary["notifications"], {"sent": 0, "failed": 0, "skipped": 0})

    def test_interval_validation(self):
        with patch.dict(os.environ, {"RADAR_SCHEDULER_INTERVAL_SECONDS": "30"}):
            self.assertEqual(scheduler._interval_seconds(), 30)
        with patch.dict(os.environ, {"RADAR_SCHEDULER_INTERVAL_SECONDS": "3600"}):
            self.assertEqual(scheduler._interval_seconds(), 3600)
        with patch.dict(os.environ, {"RADAR_SCHEDULER_INTERVAL_SECONDS": "29"}):
            with self.assertRaises(RuntimeError):
                scheduler._interval_seconds()
        with patch.dict(os.environ, {"RADAR_SCHEDULER_INTERVAL_SECONDS": "not-a-number"}):
            with self.assertRaises(RuntimeError):
                scheduler._interval_seconds()


if __name__ == "__main__":
    unittest.main()
