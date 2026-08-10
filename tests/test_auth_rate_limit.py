from __future__ import annotations

import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar.application import create_app
from radar.auth import hash_password
from radar.db import connect


class AuthRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "radar.db"
        os.environ["RADAR_DB"] = str(self.db)
        os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
        os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
        os.environ["ADMIN_USERNAME"] = "admin"
        os.environ["ADMIN_EMAIL"] = "admin@example.com"
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password("correct-horse-battery")
        self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()
        for key in (
            "RADAR_DB", "SECRET_KEY", "ENCRYPTION_KEY", "ADMIN_USERNAME",
            "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH",
        ):
            os.environ.pop(key, None)

    def _csrf(self) -> str:
        self.client.get("/login")
        with self.client.session_transaction() as session:
            return str(session["csrf_token"])

    def test_login_is_throttled_after_repeated_failures(self):
        csrf = self._csrf()
        with patch("radar.web.verify_password", return_value=False):
            for _ in range(8):
                response = self.client.post(
                    "/login",
                    data={"csrf_token": csrf, "username": "admin", "password": "wrong-password"},
                )
                self.assertEqual(response.status_code, 200)

            blocked = self.client.post(
                "/login",
                data={"csrf_token": csrf, "username": "admin", "password": "wrong-password"},
            )

        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Too many sign-in attempts", blocked.get_data(as_text=True))

    def test_successful_login_clears_username_failure_counter(self):
        csrf = self._csrf()
        with patch("radar.web.verify_password", return_value=False):
            for _ in range(3):
                self.client.post(
                    "/login",
                    data={"csrf_token": csrf, "username": "admin", "password": "wrong-password"},
                )

        with patch("radar.web.verify_password", return_value=True):
            success = self.client.post(
                "/login",
                data={"csrf_token": csrf, "username": "admin", "password": "correct-horse-battery"},
            )
        self.assertEqual(success.status_code, 302)

        with connect() as conn:
            rows = conn.execute("SELECT key, failures FROM auth_rate_limits").fetchall()
        # The IP counter remains to stop one valid account from clearing
        # brute-force attempts against other accounts. The username counter is cleared.
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["failures"]), 3)

    def test_password_reset_requests_are_throttled_without_account_enumeration(self):
        csrf = self._csrf()
        for _ in range(3):
            response = self.client.post(
                "/forgot-password",
                data={"csrf_token": csrf, "identity": "nobody@example.com"},
            )
            self.assertEqual(response.status_code, 302)

        blocked = self.client.post(
            "/forgot-password",
            data={"csrf_token": csrf, "identity": "nobody@example.com"},
        )
        self.assertEqual(blocked.status_code, 302)
        follow = self.client.get(blocked.headers["Location"])
        self.assertIn(
            "If that active account has an email address and SMTP is configured",
            follow.get_data(as_text=True),
        )


if __name__ == "__main__":
    unittest.main()
