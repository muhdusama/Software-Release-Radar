from datetime import datetime, timedelta, timezone
import unittest

from radar.tracker_utils import is_due


class DueSchedulingTests(unittest.TestCase):
    def test_never_checked_tracker_is_due(self):
        now = datetime(2026, 8, 8, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(is_due(None, 24, now=now))

    def test_recent_tracker_is_not_due(self):
        now = datetime(2026, 8, 8, 0, 0, tzinfo=timezone.utc)
        last_checked = (now - timedelta(hours=23)).isoformat()
        self.assertFalse(is_due(last_checked, 24, now=now))

    def test_expired_tracker_is_due(self):
        now = datetime(2026, 8, 8, 0, 0, tzinfo=timezone.utc)
        last_checked = (now - timedelta(hours=24)).isoformat()
        self.assertTrue(is_due(last_checked, 24, now=now))


if __name__ == "__main__":
    unittest.main()
