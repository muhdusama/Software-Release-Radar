from __future__ import annotations

import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar import web
from radar.auth import hash_password
from radar.db import set_settings

_ENV_KEYS = (
    "RADAR_DB", "SECRET_KEY", "ENCRYPTION_KEY", "ADMIN_USERNAME",
    "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH",
)


class AppFactoryTests(unittest.TestCase):
    """radar.web.create_app is the single factory and carries every protection."""

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

    def test_web_factory_password_reset_ignores_the_request_host(self):
        app = web.create_app()
        app.testing = True
        client = app.test_client()
        set_settings({"app_base_url": "https://radar.example.test"})
        hostile = "http://attacker.example"
        client.get("/forgot-password", base_url=hostile)
        with client.session_transaction(base_url=hostile) as session:
            csrf = session["csrf_token"]
        with (
            patch("radar.security_controls._minimum_reset_delay"),
            patch("radar.security_controls._enqueue_email", return_value=True) as enqueue,
        ):
            response = client.post(
                "/forgot-password", base_url=hostile,
                data={"csrf_token": csrf, "identity": "admin"},
            )
        self.assertEqual(response.status_code, 302)
        body = str(enqueue.call_args.args[2])
        self.assertIn("https://radar.example.test/reset-password/", body)
        self.assertNotIn("attacker.example", body)

    def test_no_module_replaces_registered_view_functions(self):
        root = Path(__file__).parents[1] / "radar"
        for path in root.rglob("*.py"):
            with self.subTest(path=path.name):
                self.assertNotIn("view_functions[", path.read_text())


if __name__ == "__main__":
    unittest.main()
