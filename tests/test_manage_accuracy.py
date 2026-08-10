from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from radar import db, manage


class ManageAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db = os.environ.get("RADAR_DB")
        os.environ["RADAR_DB"] = str(Path(self.tempdir.name) / "radar.db")
        db.init_db()
        now = db.utcnow()
        trackers = [
            ("linuxserver-update", "example/linuxserver-update", "v0.9.2-ls171", "v0.9.2-ls171", "v0.9.2-ls170", "ok", None, "ok", None),
            ("missing-upstream", "example/missing-upstream", None, None, "2.36.0", None, None, "ok", None),
            ("checker-error", "example/checker-error", "1.1.0", "v1.1.0", "1.0.0", "error", "checker failed", "ok", None),
            ("offline-update", "example/offline-update", "2.0.0", "v2.0.0", "1.0.0", "ok", None, "error", "connection refused"),
            ("current", "example/current", "3.0.0", "v3.0.0", "3.0.0", "ok", None, "ok", None),
            ("uncomparable", "example/uncomparable", "v0.5.5", "desktop-v0.5.5", "main", "ok", None, "ok", None),
            ("stale-decision", "example/stale-decision", "4.0.0", "v4.0.0", "4.0.0", "ok", None, "ok", None),
        ]
        with db.transaction() as conn:
            for name, repo, current_version, release_name, installed, last_status, last_error, probe_status, probe_error in trackers:
                conn.execute(
                    """
                    INSERT INTO trackers
                        (name, repository, current_version, current_release_name,
                         installed_version, last_status, last_error,
                         last_probe_status, last_probe_error, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, repo, current_version, release_name, installed, last_status, last_error, probe_status, probe_error, now, now),
                )
            stale_id = conn.execute("SELECT id FROM trackers WHERE name='stale-decision'").fetchone()[0]
            conn.execute(
                """
                INSERT INTO upgrade_decisions
                    (tracker_id, release_version, release_name, installed_version_at_decision,
                     decision_status, priority, risk, checklist_json, created_at, updated_at)
                VALUES (?, '4.0.0', 'v4.0.0', '3.9.0', 'wait', 'high', 'low', '[]', ?, ?)
                """,
                (stale_id, now, now),
            )

    def tearDown(self):
        if self.old_db is None:
            os.environ.pop("RADAR_DB", None)
        else:
            os.environ["RADAR_DB"] = self.old_db
        self.tempdir.cleanup()

    def capture(self, function):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = function(argparse.Namespace())
        self.assertEqual(code, 0)
        return json.loads(stream.getvalue())

    def test_status_and_upgrades_use_identical_update_count(self):
        status = self.capture(manage.status)
        upgrades = self.capture(manage.upgrades)
        self.assertEqual(status["trackers"]["updates_available"], 2)
        self.assertEqual(upgrades["count"], 2)
        self.assertEqual(upgrades["updates_available"], 2)
        self.assertEqual(status["trackers"]["updates_available"], upgrades["count"])

    def test_needs_attention_is_separate(self):
        status = self.capture(manage.status)
        upgrades = self.capture(manage.upgrades)
        self.assertEqual(status["trackers"]["needs_attention"], 4)
        self.assertEqual(upgrades["needs_attention_count"], 4)
        names = {item["name"] for item in upgrades["needs_attention"]}
        self.assertEqual(names, {"missing-upstream", "checker-error", "offline-update", "uncomparable"})

    def test_stale_decision_does_not_inflate_upgrade_queue(self):
        upgrades = self.capture(manage.upgrades)
        names = {item["name"] for item in upgrades["upgrades"]}
        self.assertNotIn("stale-decision", names)


if __name__ == "__main__":
    unittest.main()
