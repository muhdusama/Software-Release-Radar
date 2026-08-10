from __future__ import annotations

import unittest

from radar.notifications import notification_smoke_payload


class NotificationSmokeTests(unittest.TestCase):
    def test_payload_is_deterministic_and_non_llm(self):
        first = notification_smoke_payload()
        second = notification_smoke_payload()
        self.assertEqual(first, second)
        self.assertEqual(first["title"], "Software Release Radar notification smoke test")
        self.assertIn("No software was installed, updated, restarted, or changed.", first["message"])
        self.assertIsNone(first["url"])


if __name__ == "__main__":
    unittest.main()
