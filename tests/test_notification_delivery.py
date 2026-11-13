from __future__ import annotations

import base64
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from radar import checker, notifications, system_channels
from radar.auth import hash_password
from radar.db import connect, get_settings, init_db, set_settings, transaction, utcnow
from radar.secrets_store import encrypt_secret


class DeliveryTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["RADAR_DB"] = str(Path(self.tempdir.name) / "radar.db")
        os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
        os.environ["ADMIN_USERNAME"] = "admin"
        os.environ["ADMIN_EMAIL"] = "admin@example.com"
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password("correct-horse-battery")
        init_db()
        notifications.ensure_notification_preferences()
        with transaction() as conn:
            conn.execute(
                "UPDATE users SET notify_email = 0, notify_pushover = 1, pushover_user_key_enc = ?",
                (encrypt_secret("user-key"),),
            )

    def tearDown(self):
        self.tempdir.cleanup()
        for key in ("RADAR_DB", "ENCRYPTION_KEY", "ADMIN_USERNAME", "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH"):
            os.environ.pop(key, None)

    def add_event(self, version="1.0", detected_at=None) -> int:
        now = utcnow()
        with transaction() as conn:
            row = conn.execute("SELECT id FROM trackers WHERE repository = 'o/r'").fetchone()
            if row is None:
                tracker = int(conn.execute(
                    "INSERT INTO trackers (name, repository, created_at, updated_at) VALUES ('App', 'o/r', ?, ?)",
                    (now, now),
                ).lastrowid)
            else:
                tracker = int(row["id"])
            return int(conn.execute(
                "INSERT INTO events (tracker_id, version, detected_at) VALUES (?, ?, ?)",
                (tracker, version, detected_at or now),
            ).lastrowid)

    def notified(self, event_id):
        with connect() as conn:
            return conn.execute("SELECT notified_at FROM events WHERE id = ?", (event_id,)).fetchone()[0]

    def backdate_attempts(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        with transaction() as conn:
            conn.execute("UPDATE notification_deliveries SET last_attempt_at = ?", (past,))
            conn.execute("UPDATE system_notification_deliveries SET last_attempt_at = ?", (past,))


class DispatchTests(DeliveryTestCase):
    def test_success_sets_notified_at(self):
        event = self.add_event()
        with patch("radar.notifications.send_pushover") as send:
            counts = notifications.dispatch_pending_notifications()
        self.assertEqual(counts["sent"], 1)
        send.assert_called_once()
        self.assertIsNotNone(self.notified(event))

    def test_no_recipients_still_closes_event(self):
        with transaction() as conn:
            conn.execute("UPDATE users SET notify_pushover = 0")
        event = self.add_event()
        notifications.dispatch_pending_notifications()
        self.assertIsNotNone(self.notified(event))

    def test_earlier_pending_events_are_retried(self):
        old = self.add_event("1.0")
        with patch("radar.notifications.send_pushover", side_effect=notifications.NotificationError("down")):
            notifications.dispatch_pending_notifications()
        self.assertIsNone(self.notified(old))
        new = self.add_event("2.0")
        self.backdate_attempts()
        with patch("radar.notifications.send_pushover") as send:
            notifications.dispatch_pending_notifications()
        self.assertEqual(send.call_count, 2)
        self.assertIsNotNone(self.notified(old))
        self.assertIsNotNone(self.notified(new))

    def test_backoff_defers_retry(self):
        event = self.add_event()
        with patch("radar.notifications.send_pushover", side_effect=OSError("down")):
            notifications.dispatch_pending_notifications()
        with patch("radar.notifications.send_pushover") as send:
            notifications.dispatch_pending_notifications()
        send.assert_not_called()
        self.assertIsNone(self.notified(event))

    def test_timeout_in_pushover_read_is_failure_not_abort(self):
        set_settings({"pushover_enabled": "1", "pushover_app_token_enc": encrypt_secret("app")})
        first, second = self.add_event("1.0"), self.add_event("2.0")
        response = MagicMock()
        response.__enter__.return_value.read.side_effect = TimeoutError("read timed out")
        calls = []

        def flaky(request, timeout):
            calls.append(1)
            if len(calls) == 1:
                return response
            ok = MagicMock()
            ok.__enter__.return_value.read.return_value = b'{"status": 1}'
            return ok

        with patch("radar.notifications.open_http", side_effect=flaky):
            counts = notifications.dispatch_release_notifications([first, second])
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(counts["sent"], 1)
        self.assertIsNone(self.notified(first))
        self.assertIsNotNone(self.notified(second))

    def test_attempts_cap_then_terminal(self):
        event = self.add_event()
        with patch("radar.notifications.send_pushover", side_effect=RuntimeError("boom")) as send:
            for _ in range(notifications.MAX_DELIVERY_ATTEMPTS + 2):
                notifications.dispatch_pending_notifications()
                self.backdate_attempts()
        self.assertEqual(send.call_count, notifications.MAX_DELIVERY_ATTEMPTS)
        self.assertIsNotNone(self.notified(event))
        with connect() as conn:
            row = conn.execute("SELECT status, attempts FROM notification_deliveries WHERE channel = 'pushover'").fetchone()
        self.assertEqual((row["status"], row["attempts"]), ("failed", notifications.MAX_DELIVERY_ATTEMPTS))
        self.assertTrue(notifications.recent_delivery_failures()[0]["exhausted"])

    def test_stale_pending_events_close_without_sending(self):
        old = (datetime.now(timezone.utc) - timedelta(days=8)).replace(microsecond=0).isoformat()
        event = self.add_event(detected_at=old)
        with patch("radar.notifications.send_pushover") as send:
            notifications.dispatch_pending_notifications()
        send.assert_not_called()
        self.assertIsNotNone(self.notified(event))

    def test_cli_notify_leaves_failed_events_pending(self):
        failed = self.add_event()
        with patch("radar.notifications.send_pushover", side_effect=OSError("down")), patch(
            "radar.checker.check_all", return_value=[]
        ), patch("sys.stdout") as out:
            self.assertEqual(checker.main(["--notify"]), 0)
        self.assertIsNone(self.notified(failed))
        out.write.assert_not_called()

    def test_disabled_provider_is_skipped_not_retried(self):
        event = self.add_event()
        notifications.dispatch_pending_notifications()
        self.assertIsNotNone(self.notified(event))
        self.assertEqual(notifications.recent_delivery_failures(), [])

    def test_auto_analysis_oserror_keeps_event_id(self):
        self.add_event()
        tracker = {"id": 1, "name": "App", "repository": "o/r", "current_version": "1.0",
                   "current_release_name": "1.0"}
        release = SimpleNamespace(version="2.0", name="2.0", url=None, published_at=None, body="")
        with patch("radar.checker.auto_analyse_event", side_effect=OSError("timed out")):
            result = checker._record_success(tracker, release)
        self.assertIsNotNone(result.event_id)
        self.assertEqual(result.status, "ok")


class SystemChannelTests(DeliveryTestCase):
    def configure(self, **values):
        set_settings({k: str(v) for k, v in values.items()})

    def capture(self):
        sent = []

        def fake(request, timeout):
            sent.append(request)
            response = MagicMock()
            response.__enter__.return_value.read.return_value = b"{}"
            return response

        return sent, patch("radar.system_channels.open_http", side_effect=fake)

    def test_webhook_payload_signature_and_delivery_once_per_event(self):
        self.configure(
            webhook_enabled=1, webhook_url="https://hooks.example.com/r",
            webhook_token_enc=encrypt_secret("tok"), webhook_secret_enc=encrypt_secret("sec"),
        )
        event = self.add_event()
        sent, patcher = self.capture()
        with patch("radar.notifications.send_pushover"), patcher:
            notifications.dispatch_pending_notifications()
            notifications.dispatch_pending_notifications()
        self.assertEqual(len(sent), 1)
        request = sent[0]
        import hashlib, hmac, json
        body = json.loads(request.data)
        self.assertEqual(body["event"], "release.detected")
        self.assertEqual(body["software"], "App")
        self.assertEqual(body["new_version"], "1.0")
        self.assertNotIn("release_body", body)
        self.assertEqual(request.get_header("Authorization"), "Bearer tok")
        expected = "sha256=" + hmac.new(b"sec", request.data, hashlib.sha256).hexdigest()
        self.assertEqual(request.get_header("X-radar-signature"), expected)
        self.assertIsNotNone(self.notified(event))

    def test_ntfy_and_gotify_requests(self):
        self.configure(
            ntfy_enabled=1, ntfy_topic="alerts", ntfy_server_url="https://ntfy.sh",
            gotify_enabled=1, gotify_url="https://gotify.example.com/",
            gotify_token_enc=encrypt_secret("gt"),
        )
        self.add_event()
        sent, patcher = self.capture()
        with patch("radar.notifications.send_pushover"), patcher:
            notifications.dispatch_pending_notifications()
        urls = {r.full_url: r for r in sent}
        import json
        self.assertEqual(json.loads(urls["https://ntfy.sh"].data)["topic"], "alerts")
        gotify = urls["https://gotify.example.com/message"]
        self.assertEqual(gotify.get_header("X-gotify-key"), "gt")
        self.assertEqual(json.loads(gotify.data)["priority"], 5)

    def test_system_failure_is_retried_and_does_not_block_user_channel(self):
        self.configure(ntfy_enabled=1, ntfy_topic="alerts")
        event = self.add_event()
        with patch("radar.notifications.send_pushover") as push, patch(
            "radar.system_channels.open_http", side_effect=TimeoutError("slow")
        ):
            counts = notifications.dispatch_pending_notifications()
        push.assert_called_once()
        self.assertEqual((counts["sent"], counts["failed"]), (1, 1))
        self.assertIsNone(self.notified(event))
        self.backdate_attempts()
        sent, patcher = self.capture()
        with patcher:
            notifications.dispatch_pending_notifications()
        self.assertEqual(len(sent), 1)
        self.assertIsNotNone(self.notified(event))

    def test_system_channel_follows_admin_mute_and_safety_switch(self):
        self.configure(ntfy_enabled=1, ntfy_topic="alerts")
        event = self.add_event()
        with connect() as conn:
            row = conn.execute("SELECT id FROM trackers").fetchone()
        with transaction() as conn:
            conn.execute(
                "INSERT INTO tracker_notification_preferences (user_id, tracker_id, mode, updated_at) VALUES (1, ?, 'off', ?)",
                (row["id"], utcnow()),
            )
        sent, patcher = self.capture()
        with patch("radar.notifications.send_pushover"), patcher:
            notifications.dispatch_pending_notifications()
        self.assertEqual(sent, [])
        with connect() as conn:
            status = conn.execute("SELECT status FROM system_notification_deliveries").fetchone()[0]
        self.assertEqual(status, "skipped")
        self.assertIsNotNone(self.notified(event))

    def test_https_enforced_unless_loopback_or_allowed(self):
        with self.assertRaises(ValueError):
            system_channels.validate_channel_url("http://hooks.example.com/x", "Webhook URL")
        self.assertEqual(system_channels.validate_channel_url("http://127.0.0.1:8080/x", "Webhook URL"), "http://127.0.0.1:8080/x")
        with patch.dict(os.environ, {"ALLOW_INSECURE_INTEGRATIONS": "true"}):
            system_channels.validate_channel_url("http://hooks.example.com/x", "Webhook URL")
        with self.assertRaises(ValueError):
            system_channels.validate_channel_url("https://user:pw@hooks.example.com/x", "Webhook URL")

    def test_form_validation_keeps_saved_secret_and_requires_fields(self):
        form = {"gotify_enabled": "on", "gotify_url": "https://g.example.com"}
        with self.assertRaises(ValueError):
            system_channels.settings_from_form(form, {**self._raw(), "gotify_token_enc": ""})
        values = system_channels.settings_from_form(form, {**self._raw(), "gotify_token_enc": "x"})
        self.assertNotIn("gotify_token_enc", values)
        with self.assertRaises(ValueError):
            system_channels.settings_from_form({"ntfy_topic": "bad topic!"}, self._raw())

    def _raw(self):
        return {k: "" for k in system_channels.SYSTEM_CHANNEL_KEYS}


class WebTests(DeliveryTestCase):
    def client(self):
        from radar.application import create_app
        from radar.auth import token_digest

        os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
        app = create_app()
        app.testing = True
        client = app.test_client()
        with connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        with client.session_transaction() as session:
            session["user_id"] = int(user["id"])
            session["password_stamp"] = token_digest(str(user["password_hash"]))
            session["csrf_token"] = "csrf"
        return client

    def test_pages_render_save_and_hide_secrets(self):
        client = self.client()
        saved = client.post("/settings", data={
            "csrf_token": "csrf", "section": "channels", "gotify_enabled": "on",
            "gotify_url": "https://g.example.com", "gotify_token": "super-secret-token",
            "ntfy_server_url": "https://ntfy.sh",
        })
        self.assertEqual(saved.status_code, 302)
        page = client.get("/settings?section=channels").get_data(as_text=True)
        self.assertIn("Send test notification", page)
        self.assertNotIn("super-secret-token", page)
        self.add_event()
        with transaction() as conn:
            conn.execute(
                "INSERT INTO system_notification_deliveries (event_id, channel, status, error, attempts, last_attempt_at, sent_at) "
                "VALUES (1, 'gotify', 'failed', 'Gotify returned HTTP 500.', 2, ?, ?)", (utcnow(), utcnow()),
            )
        notes = client.get("/notifications").get_data(as_text=True)
        self.assertIn("Recent delivery failures", notes)
        self.assertIn("Gotify returned HTTP 500.", notes)
        self.assertIn("Ready to deliver", notes)
        self.assertEqual(client.post("/settings/test-channel/bogus", data={"csrf_token": "csrf"}).status_code, 404)
        rejected = client.post("/settings", data={
            "csrf_token": "csrf", "section": "channels", "webhook_url": "http://hooks.example.com/x"})
        self.assertEqual(rejected.status_code, 302)
        self.assertEqual(system_channels.enabled_system_channels(), ["gotify"])
        self.assertEqual(get_settings(["webhook_url"])["webhook_url"], "")


class AIClientTests(unittest.TestCase):
    def test_read_timeout_becomes_ai_client_error(self):
        from radar import ai_client

        response = MagicMock()
        response.__enter__.return_value.read.side_effect = TimeoutError("slow")
        cfg = {"enabled": True, "base_url": "https://x.example", "api_key": "k", "model": "m",
               "max_tokens": 10, "timeout": 5}
        with patch("radar.ai_client.config", return_value=cfg), patch(
            "radar.ai_client.open_http", return_value=response
        ):
            with self.assertRaises(ai_client.AIClientError):
                ai_client.chat([{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
