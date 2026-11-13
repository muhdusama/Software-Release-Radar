import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar.checker import check_tracker
from radar.db import connect, init_db, transaction, utcnow
from radar.github import GitHubError, ReleaseInfo
from radar.upgrade_workflow import checklist_from_form, load_checklist, save_upgrade_review


class ChecklistStableIdTests(unittest.TestCase):
    def test_tick_follows_item_when_items_are_added_removed_and_edited(self):
        # The operator ticked "rollback", cleared "backup", reworded "notes" and added a new item.
        items = checklist_from_form(
            ["backup", "rollback", "notes"],
            ["", "Confirm rollback", "Read the release notes twice"],
            ["rollback"],
            "Brand new step",
        )
        self.assertEqual([(item["text"], item["done"]) for item in items],
                         [("Confirm rollback", True), ("Read the release notes twice", False), ("Brand new step", False)])
        self.assertEqual([item["id"] for item in items[:2]], ["rollback", "notes"])
        self.assertNotIn(items[2]["id"], {"backup", "rollback", "notes"})

    def test_untrusted_or_duplicate_ids_are_replaced_and_never_ticked(self):
        items = checklist_from_form(["ok", "ok", "bad id!"], ["One", "Two", "Three"], ["ok", "bad id!"], "")
        self.assertEqual(items[0], {"id": "ok", "text": "One", "done": True})
        self.assertNotEqual(items[1]["id"], "ok")
        self.assertFalse(items[1]["done"])
        self.assertFalse(items[2]["done"])

    def test_form_rejects_mismatched_fields_and_too_many_items(self):
        with self.assertRaises(ValueError):
            checklist_from_form(["a"], [], [], "")
        with self.assertRaises(ValueError):
            checklist_from_form([], [], [], "\n".join(f"Item {n}" for n in range(31)))

    def test_legacy_records_without_ids_load_with_stable_ids(self):
        legacy = json.dumps([{"text": "A", "done": True}, {"text": "B", "done": False}])
        self.assertEqual(load_checklist(legacy), [{"id": "item-1", "text": "A", "done": True},
                                                  {"id": "item-2", "text": "B", "done": False}])
        self.assertEqual(load_checklist(legacy), load_checklist(legacy))


class ChecklistSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"RADAR_DB": str(Path(self.tmp.name) / "radar.db")})
        env.start()
        self.addCleanup(env.stop)
        init_db()
        with transaction() as conn:
            conn.execute("INSERT INTO trackers(id,name,repository,current_version,current_release_name,installed_version,created_at,updated_at)"
                         " VALUES(1,'Example','example/project','v2','v2','v1',?,?)", (utcnow(), utcnow()))

    def test_save_assigns_missing_ids_and_keeps_given_ids(self):
        saved = save_upgrade_review(1, "v2", 0, {"checklist": [{"id": "keep", "text": "A", "done": True},
                                                               {"id": None, "text": "B", "done": False},
                                                               {"text": "C", "done": False}]},
                                    user_id=None, cli=True)
        checklist = json.loads(saved["checklist_json"])
        self.assertEqual(checklist[0], {"id": "keep", "text": "A", "done": True})
        self.assertEqual(len({item["id"] for item in checklist}), 3)

    def test_save_rejects_duplicate_or_malformed_ids(self):
        for checklist in ([{"id": "x", "text": "A", "done": False}, {"id": "x", "text": "B", "done": False}],
                          [{"id": "bad id", "text": "A", "done": False}]):
            with self.assertRaises(ValueError):
                save_upgrade_review(1, "v2", 0, {"checklist": checklist}, user_id=None, cli=True)


class FirstRunHistorySeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"RADAR_DB": str(Path(self.tmp.name) / "radar.db")})
        env.start()
        self.addCleanup(env.stop)
        init_db()

    def add_tracker(self, strategy="release"):
        with transaction() as conn:
            cursor = conn.execute("INSERT INTO trackers(name,repository,strategy,installed_version,created_at,updated_at)"
                                  " VALUES('Example',?,?,'v1',?,?)", (f'example/{strategy}', strategy, utcnow(), utcnow()))
            return int(cursor.lastrowid)

    @staticmethod
    def releases():
        return [ReleaseInfo(f"v{n}", f"Example {n}", f"https://example.invalid/v{n}", f"2026-0{n}-01T10:00:00Z", f"Notes {n}")
                for n in (3, 2, 1)]

    def events(self, tracker_id):
        with connect() as conn:
            return conn.execute("SELECT * FROM events WHERE tracker_id=? ORDER BY detected_at DESC", (tracker_id,)).fetchall()

    def test_first_check_seeds_history_without_alerting(self):
        tracker_id = self.add_tracker()
        releases = self.releases()
        with patch("radar.checker.get_latest", return_value=releases[0]), \
             patch("radar.checker.get_recent_releases", return_value=releases) as recent:
            result = check_tracker(tracker_id, run_probe=False)
            self.assertTrue(result.baseline)
            self.assertIsNone(result.event_id)
            check_tracker(tracker_id, baseline=True, run_probe=False)
        recent.assert_called_once()
        events = self.events(tracker_id)
        self.assertEqual([row["version"] for row in events], ["v3", "v2", "v1"])
        self.assertEqual([row["previous_version"] for row in events], ["v2", "v1", None])
        self.assertEqual(events[0]["detected_at"], "2026-03-01T10:00:00+00:00")
        self.assertTrue(all(row["notified_at"] for row in events))

    def test_tag_trackers_and_seed_failures_leave_the_baseline_intact(self):
        tag_tracker = self.add_tracker(strategy="tag")
        release_tracker = self.add_tracker()
        with patch("radar.checker.get_latest", return_value=self.releases()[0]), \
             patch("radar.checker.get_recent_releases", side_effect=GitHubError("down")) as recent:
            self.assertEqual(check_tracker(tag_tracker, run_probe=False).status, "ok")
            self.assertEqual(check_tracker(release_tracker, run_probe=False).status, "ok")
        recent.assert_called_once()
        self.assertEqual(self.events(tag_tracker), [])
        self.assertEqual(self.events(release_tracker), [])


if __name__ == "__main__":
    unittest.main()
