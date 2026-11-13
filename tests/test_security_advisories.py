import unittest
from unittest.mock import patch

import test_mcp_auth as fixtures
from radar import advisories
from radar.advisories import evaluate, in_range
from radar.db import connect, transaction, utcnow

GITEA = {
    "ghsa_id": "GHSA-mf6p-vqpw-3r7x", "cve_id": "CVE-2026-116474", "severity": "medium",
    "summary": "Actions token can spoof <b>signed</b> commits", "html_url": "https://github.com/o/app/security/advisories/GHSA-mf6p-vqpw-3r7x",
    "published_at": "2026-11-01T09:42:47Z",
    "vulnerabilities": [{"package": {"ecosystem": "go", "name": "gitea.dev"},
                         "vulnerable_version_range": ">= 1.19.0, <= 28.2.0", "patched_versions": "28.3.0"}],
}
RUNNER = {
    "ghsa_id": "GHSA-7c33-wq58-g35r", "cve_id": None, "severity": "high", "summary": "Runner cache poisoning",
    "html_url": "https://github.com/o/app/security/advisories/GHSA-7c33-wq58-g35r", "published_at": "2026-11-13T07:00:02Z",
    "vulnerabilities": [{"package": {"ecosystem": "go", "name": "gitea.com/gitea/runner"},
                         "vulnerable_version_range": "< 5.3.0", "patched_versions": "5.3.0"}],
}


class RangeTests(unittest.TestCase):
    def test_ranges(self):
        self.assertTrue(in_range("v1.22.0", ">= 1.19.0, <= 28.2.0"))
        self.assertFalse(in_range("28.3.0", ">= 1.19.0, <= 28.2.0"))
        self.assertFalse(in_range("1.18.9", ">= 1.19.0, <= 28.2.0"))
        self.assertTrue(in_range("5.2.9", "< 5.3.0"))
        self.assertTrue(in_range("2.0.0", "= 2.0.0"))
        self.assertIsNone(in_range("nightly", "< 5.3.0"))
        self.assertIsNone(in_range("1.0.0", "between one and two"))


class EvaluateTests(unittest.TestCase):
    known = ["v28.3.0", "v28.2.0", "v1.22.0"]

    def project(self, payload):
        return advisories._project(payload)

    def test_affected_and_fixed_by_target(self):
        result = evaluate(self.project(GITEA), "v1.22.0", "v28.3.0", self.known)
        self.assertEqual((result["status"], result["fixed_in"], result["target_fixes"]), ("affected", "28.3.0", True))

    def test_not_affected_after_fix(self):
        self.assertEqual(evaluate(self.project(GITEA), "v28.3.0", "v28.3.0", self.known)["status"], "not_affected")

    def test_other_component_is_never_counted_against_the_tracker(self):
        result = evaluate(self.project(RUNNER), "v1.22.0", "v28.3.0", self.known)
        self.assertEqual((result["status"], result["packages"]), ("other_component", ["gitea.com/gitea/runner"]))

    def test_unknown_installed_version(self):
        self.assertEqual(evaluate(self.project(GITEA), None, "v28.3.0", self.known)["status"], "unknown")

    def test_projection_rejects_malformed_ids_and_foreign_urls(self):
        self.assertIsNone(advisories._project({"ghsa_id": "GHSA-nope"}))
        projected = self.project({**GITEA, "html_url": "https://evil.invalid/x", "severity": "catastrophic"})
        self.assertEqual(projected["url"], "https://github.com/advisories/GHSA-mf6p-vqpw-3r7x")
        self.assertEqual(projected["severity"], "unknown")


class AdvisoryPagesTests(unittest.TestCase):
    setUp = fixtures.MCPAuthTests.setUp
    login = fixtures.MCPAuthTests.login
    key = fixtures.MCPAuthTests.key

    def add_tracker(self):
        with transaction() as conn:
            tracker_id = conn.execute(
                "INSERT INTO trackers(name,repository,current_version,current_release_name,installed_version,last_status,created_at,updated_at)"
                " VALUES('Gitea','go-gitea/gitea','v28.3.0','v28.3.0','v1.22.0','ok',?,?)", (utcnow(), utcnow())).lastrowid
            conn.execute("INSERT INTO events(tracker_id,version,release_name,detected_at,notified_at) VALUES(?,?,?,?,?)",
                         (tracker_id, "v28.2.0", "v28.2.0", "2026-10-19T00:00:00+00:00", utcnow()))
        return tracker_id

    def test_scheduler_refresh_stores_advisories_daily(self):
        tracker_id = self.add_tracker()
        with patch("radar.advisories._github_get", return_value=[GITEA, RUNNER, {"ghsa_id": "bad"}]) as fetch:
            self.assertEqual(advisories.refresh_due_advisories(), {"refreshed": 1, "failed": 0})
            self.assertEqual(advisories.refresh_due_advisories(), {"refreshed": 0, "failed": 0})
        fetch.assert_called_once_with("/repos/go-gitea/gitea/security-advisories?state=published&per_page=100")
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM security_advisories WHERE tracker_id=?", (tracker_id,)).fetchone()[0], 2)

    def test_failed_refresh_backs_off_and_forges_are_skipped(self):
        self.add_tracker()
        with transaction() as conn:
            conn.execute("INSERT INTO trackers(name,repository,last_status,created_at,updated_at) VALUES('F','codeberg.org/o/r','ok',?,?)",
                         (utcnow(), utcnow()))
        with patch("radar.advisories._github_get", side_effect=ValueError("down")) as fetch:
            self.assertEqual(advisories.refresh_due_advisories(), {"refreshed": 0, "failed": 1})
            self.assertEqual(advisories.refresh_due_advisories(), {"refreshed": 0, "failed": 0})
        fetch.assert_called_once()

    def test_plan_dashboard_queue_and_metrics(self):
        tracker_id = self.add_tracker()
        with patch("radar.advisories._github_get", return_value=[GITEA, RUNNER]):
            advisories.refresh_due_advisories()
        self.login()
        plan = self.client.get(f"/upgrades/{tracker_id}").get_data(as_text=True)
        self.assertIn("1 published advisory affects v1.22.0.", plan)
        self.assertIn("Fixed by upgrading to v28.3.0", plan)
        self.assertIn("Applies to gitea.com/gitea/runner", plan)
        self.assertIn("&lt;b&gt;signed&lt;/b&gt;", plan)
        self.assertIn(">1 advisory</span>", self.client.get("/").get_data(as_text=True))
        self.assertIn(">1 advisory</span>", self.client.get("/upgrades").get_data(as_text=True))
        _, token = self.key()
        metrics = self.client.get("/metrics", headers={"Authorization": f"Bearer {token}"}).get_data(as_text=True)
        self.assertIn('worst_severity="medium"} 1', metrics)
        self.assertIn("srr_security_advisories_affecting 1", metrics)


if __name__ == "__main__":
    unittest.main()
