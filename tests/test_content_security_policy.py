from __future__ import annotations

import base64
import os
import re
import tempfile
import unittest
from pathlib import Path

from radar import db
from radar.application import create_app
from radar.auth import hash_password, token_digest

_ENV_KEYS = (
    "RADAR_DB", "SECRET_KEY", "ENCRYPTION_KEY", "ADMIN_USERNAME",
    "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH",
)
_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)(?![^>]*type=\"application/json\")[^>]*>", re.I)
_INLINE_HANDLER = re.compile(r"<[^>]+\son[a-z]+\s*=", re.I)
_SCRIPT_SRC = re.compile(r"<script[^>]*\bsrc=\"([^\"]+)\"", re.I)


class ContentSecurityPolicyTests(unittest.TestCase):
    """Pages must work under a script-src 'self' policy with no inline script."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_env = {key: os.environ.get(key) for key in _ENV_KEYS}
        os.environ["RADAR_DB"] = str(Path(self.tempdir.name) / "radar.db")
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
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _login(self):
        with db.connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        with self.client.session_transaction() as session:
            session["user_id"] = int(user["id"])
            session["password_stamp"] = token_digest(str(user["password_hash"]))

    def test_policy_disallows_inline_script(self):
        policy = self.client.get("/login").headers["Content-Security-Policy"]
        script_src = next(part for part in policy.split(";") if part.strip().startswith("script-src"))
        self.assertEqual(script_src.strip(), "script-src 'self'")

    def test_pages_have_no_inline_script_and_scripts_resolve(self):
        self._login()
        db.set_settings({"portainer_enabled": "1"})
        with db.transaction() as conn:
            now = db.utcnow()
            conn.execute(
                "INSERT INTO trackers (name, repository, created_at, updated_at) VALUES (?, ?, ?, ?)",
                ("Example", "example/example", now, now),
            )
        pages = (
            "/", "/upgrades", "/fleet", "/history", "/settings", "/users", "/users/new",
            "/trackers/new", "/trackers/1/edit", "/notifications", "/portainer", "/profile",
            "/about", "/revisions", "/roadmap",
        )
        for path in pages:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIsNone(_INLINE_SCRIPT.search(html))
                self.assertIsNone(_INLINE_HANDLER.search(html))
                for src in _SCRIPT_SRC.findall(html):
                    self.assertIn("v=", src)
                    asset = self.client.get(src)
                    asset.close()
                    self.assertEqual(asset.status_code, 200, src)


if __name__ == "__main__":
    unittest.main()
