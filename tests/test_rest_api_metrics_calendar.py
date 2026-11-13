"""Read-only REST API, Prometheus metrics and the maintenance calendar feed."""
import re
import unittest

import test_mcp_auth as fixtures
from radar.db import connect, set_settings, transaction, utcnow


class RestApiTests(unittest.TestCase):
    setUp = fixtures.MCPAuthTests.setUp
    key = fixtures.MCPAuthTests.key
    login = fixtures.MCPAuthTests.login

    def add_tracker(self, name="Example", repository="example/project", **extra):
        values = {"name": name, "repository": repository, "current_version": "v2.0.0", "current_release_name": "v2.0.0",
                  "installed_version": "v1.0.0", "last_status": "ok", "last_checked_at": utcnow(),
                  "created_at": utcnow(), "updated_at": utcnow(), **extra}
        with transaction() as conn:
            columns = ",".join(values)
            return conn.execute(f"INSERT INTO trackers({columns}) VALUES({','.join('?' for _ in values)})",
                                list(values.values())).lastrowid

    def bearer(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_requires_authentication(self):
        response = self.client.get("/api/v1/trackers")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Bearer", response.headers["WWW-Authenticate"])
        self.assertEqual(self.client.get("/metrics").status_code, 401)

    def test_bearer_key_reads_and_is_audited(self):
        tracker_id = self.add_tracker()
        key_id, token = self.key()
        listing = self.client.get("/api/v1/trackers?limit=10", headers=self.bearer(token))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.headers["Cache-Control"], "no-store")
        self.assertEqual([item["id"] for item in listing.get_json()["items"]], [tracker_id])
        self.assertIn("probe", listing.get_json()["items"][0])  # administrator projection
        self.assertEqual(self.client.get(f"/api/v1/trackers/{tracker_id}", headers=self.bearer(token)).get_json()["name"], "Example")
        self.assertEqual(self.client.get(f"/api/v1/trackers/{tracker_id}/upgrade", headers=self.bearer(token)).get_json()["release_key"], "v2.0.0")
        self.assertEqual(self.client.get("/api/v1/trackers/999", headers=self.bearer(token)).status_code, 404)
        with connect() as conn:
            audited = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='mcp_read' AND api_key_id=?", (key_id,)).fetchone()[0]
        self.assertGreaterEqual(audited, 3)

    def test_invalid_parameters_and_keys(self):
        _, token = self.key()
        self.assertEqual(self.client.get("/api/v1/trackers?limit=500", headers=self.bearer(token)).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/trackers?limit=abc", headers=self.bearer(token)).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/history?since=yesterday", headers=self.bearer(token)).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/status", headers=self.bearer("srr_" + "0" * 16 + "_" + "a" * 43)).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/status", headers={"Authorization": "Basic abc"}).status_code, 401)

    def test_repeated_bad_keys_are_throttled(self):
        for _ in range(20):
            self.client.get("/api/v1/status", headers=self.bearer("srr_bad"))
        _, token = self.key()
        self.assertEqual(self.client.get("/api/v1/status", headers=self.bearer(token)).status_code, 429)

    def test_disabled_mcp_policy_disables_api_keys(self):
        _, token = self.key()
        set_settings({"mcp_enabled": "0"})
        self.assertEqual(self.client.get("/api/v1/status", headers=self.bearer(token)).status_code, 401)

    def test_browser_session_reads_without_audit_and_non_admin_projection(self):
        self.add_tracker()
        self.client.get("/login")
        with self.client.session_transaction() as session:
            csrf = session["csrf_token"]
        self.client.post("/login", data={"csrf_token": csrf, "username": "reader", "password": "correct-horse-battery"})
        response = self.client.get("/api/v1/trackers?q=exam")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("probe", response.get_json()["items"][0])
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='mcp_read'").fetchone()[0], 0)


class MetricsAndCalendarTests(unittest.TestCase):
    setUp = fixtures.MCPAuthTests.setUp
    key = fixtures.MCPAuthTests.key
    login = fixtures.MCPAuthTests.login
    add_tracker = RestApiTests.add_tracker

    def test_metrics_exposition(self):
        self.add_tracker(name='Quote "and" slash\\', last_probe_status="ok", last_probe_latency_ms=12)
        self.add_tracker(name="Broken", repository="example/broken", last_status="error")
        _, token = self.key()
        response = self.client.get("/metrics", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["Content-Type"].startswith("text/plain; version=0.0.4"))
        body = response.get_data(as_text=True)
        self.assertIn('srr_trackers{state="enabled"} 2', body)
        self.assertIn('name="Quote \\"and\\" slash\\\\"', body)
        self.assertIn("srr_updates_available 1", body)
        self.assertIn("srr_trackers_needing_attention 1", body)
        self.assertIn("srr_tracker_probe_latency_milliseconds{", body)
        self.assertRegex(body, r'srr_tracker_check_success\{tracker_id="\d+",name="Broken",repository="example/broken"\} 0')
        for line in body.splitlines():
            self.assertRegex(line, r'^(# (HELP|TYPE) \w+ .+|\w+(\{.*\})? -?[0-9.e+]+)$')

    def test_calendar_link_lifecycle_and_feed(self):
        tracker_id = self.add_tracker(name="Calendar, app")
        with transaction() as conn:
            conn.execute("INSERT INTO upgrade_decisions(tracker_id,release_version,decision_status,priority,risk,"
                         "maintenance_date,checklist_json,created_at,updated_at,revision) VALUES(?,?,?,?,?,?,?,?,?,1)",
                         (tracker_id, "v2.0.0", "update", "high", "low", "2026-12-01", "[]", utcnow(), utcnow()))
        csrf = self.login()
        created = self.client.post("/profile/calendar", data={"csrf_token": csrf, "action": "create"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.headers["Cache-Control"], "no-store")
        url = re.search(r"<code>(http://localhost/calendar/cal_[^<]+\.ics)</code>", created.get_data(as_text=True)).group(1)
        path = url.removeprefix("http://localhost")
        feed = self.client.get(path)
        self.assertEqual(feed.status_code, 200)
        text = feed.get_data(as_text=True)
        self.assertIn("BEGIN:VCALENDAR\r\n", text)
        self.assertIn("DTSTART;VALUE=DATE:20261201\r\n", text)
        self.assertIn("SUMMARY:Upgrade Calendar\\, app to v2.0.0\r\n", text)
        self.assertTrue(all(len(line.encode()) <= 75 for line in text.split("\r\n")))
        self.assertEqual(self.client.get("/calendar/cal_wrong.ics").status_code, 404)
        self.assertEqual(self.client.post("/profile/calendar", data={"action": "revoke"}).status_code, 400)
        self.client.post("/profile/calendar", data={"csrf_token": csrf, "action": "revoke"})
        self.assertEqual(self.client.get(path).status_code, 404)


if __name__ == "__main__":
    unittest.main()
