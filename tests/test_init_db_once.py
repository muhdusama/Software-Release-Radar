from __future__ import annotations

import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from radar import db
from radar.application import create_app
from radar.auth import hash_password, token_digest
from radar.checker import check_all

_ENV_KEYS = (
    "RADAR_DB", "SECRET_KEY", "ENCRYPTION_KEY", "ADMIN_USERNAME",
    "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH",
)


class InitDbOnceTests(unittest.TestCase):
    """Schema setup runs at process start, never on the request or scheduler path."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_env = {key: os.environ.get(key) for key in _ENV_KEYS}
        os.environ["RADAR_DB"] = str(Path(self.tempdir.name) / "radar.db")
        os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
        os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
        os.environ["ADMIN_USERNAME"] = "admin"
        os.environ["ADMIN_EMAIL"] = "admin@example.com"
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password("correct-horse-battery")

    def tearDown(self):
        self.tempdir.cleanup()
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _no_init_db(self):
        return mock.patch.object(
            db, "init_db", side_effect=AssertionError("init_db must only run at startup")
        )

    def test_settings_reads_and_scheduler_checks_do_not_rerun_schema_setup(self):
        db.init_db()
        db.set_settings({"smtp_host": "mail.example"})
        with self._no_init_db():
            self.assertEqual(db.get_setting("smtp_host"), "mail.example")
            self.assertEqual(db.get_setting("missing", "fallback"), "fallback")
            self.assertEqual(
                db.get_settings(["smtp_host", "missing"]),
                {"smtp_host": "mail.example", "missing": ""},
            )
            self.assertEqual(check_all(enabled_only=True, due_only=True), [])

    def test_web_requests_do_not_rerun_schema_setup(self):
        app = create_app()
        app.testing = True
        with db.connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user["id"])
            session["password_stamp"] = token_digest(str(user["password_hash"]))
        with self._no_init_db():
            for path in ("/", "/settings", "/upgrades", "/fleet"):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 200)


if __name__ == "__main__":
    unittest.main()
