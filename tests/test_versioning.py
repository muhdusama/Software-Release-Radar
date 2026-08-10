from __future__ import annotations

import unittest

from radar.versioning import classify_tracker_state, classify_upgrade, versions_match


class VersioningTests(unittest.TestCase):
    def test_null_upstream_is_not_an_update(self):
        result = classify_upgrade("2.36.0", None, None)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "upstream_version_unavailable")

    def test_genuine_patch_update(self):
        result = classify_upgrade("1.2.3", "v1.2.4", "v1.2.4")
        self.assertTrue(result["available"])
        self.assertEqual(result["level"], "patch")

    def test_linuxserver_build_suffix_update(self):
        result = classify_upgrade("v0.9.2-ls170", "v0.9.2-ls171", "v0.9.2-ls171")
        self.assertTrue(result["available"])
        self.assertEqual(result["level"], "patch")

    def test_linuxserver_four_part_build_suffix_update(self):
        result = classify_upgrade("2.5.2.5491-ls155", "2.5.2.5491-ls156", "2.5.2.5491-ls156")
        self.assertTrue(result["available"])

    def test_installed_newer_than_upstream_is_not_update(self):
        result = classify_upgrade("2.6.2", "v2.6", "v2.6")
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "installed_newer")

    def test_build_metadata_can_match_base_release(self):
        self.assertTrue(versions_match("0.9.5-3144", "v0.9.5", "v0.9.5"))
        self.assertTrue(versions_match("0.26.0.0+e42a525d", "0.26.0", "0.26.0"))

    def test_unparseable_installed_version_is_not_update(self):
        result = classify_upgrade("main", "desktop-v0.5.5", "desktop-v0.5.5")
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "comparison_unavailable")

    def test_checker_failure_excludes_cached_update(self):
        state = classify_tracker_state({
            "installed_version": "1.0.0",
            "current_version": "1.1.0",
            "current_release_name": "v1.1.0",
            "last_status": "error",
            "last_error": "rate limited",
            "last_probe_status": "ok",
        })
        self.assertFalse(state["update_available"])
        self.assertIn("checker_error", state["attention_reasons"])

    def test_offline_tracker_can_be_update_and_attention(self):
        state = classify_tracker_state({
            "installed_version": "1.0.0",
            "current_version": "1.1.0",
            "current_release_name": "v1.1.0",
            "last_status": "ok",
            "last_probe_status": "error",
            "last_probe_error": "connection refused",
        })
        self.assertTrue(state["update_available"])
        self.assertTrue(state["needs_attention"])
        self.assertIn("offline", state["attention_reasons"])


if __name__ == "__main__":
    unittest.main()
