"""Proxy sign-in trusts a username header only from configured proxy peers."""
import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar.auth import hash_password
from radar.web import create_app


class ForwardAuthTests(unittest.TestCase):
    def make_app(self, **extra):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict(os.environ, {
            "RADAR_DB": str(Path(tmp.name) / "radar.db"),
            "SECRET_KEY": "local-test-secret-key-at-least-32-characters",
            "ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
            "ADMIN_USERNAME": "admin", "ADMIN_PASSWORD_HASH": hash_password("correct-horse-battery", iterations=1000),
            "RADAR_FORWARD_AUTH_HEADER": "Remote-User", "RADAR_FORWARD_AUTH_TRUSTED_PROXIES": "10.0.0.0/8, 192.168.10.106",
            **extra,
        })
        env.start()
        self.addCleanup(env.stop)
        app = create_app()
        app.testing = True
        return app.test_client()

    def get(self, client, peer, user=None, **headers):
        if user is not None:
            headers["Remote-User"] = user
        return client.get("/", headers=headers, environ_base={"REMOTE_ADDR": peer})

    def test_trusted_proxy_signs_in_existing_user(self):
        client = self.make_app()
        response = self.get(client, "192.168.10.106", "ADMIN")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get(client, "10.20.30.40", "admin").status_code, 200)

    def test_header_is_ignored_from_untrusted_peers(self):
        client = self.make_app()
        response = self.get(client, "192.0.2.50", "admin")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_spoofed_forwarded_for_does_not_make_a_peer_trusted(self):
        client = self.make_app(TRUST_PROXY_HEADERS="true")
        response = self.get(client, "192.0.2.50", "admin", **{"X-Forwarded-For": "192.168.10.106"})
        self.assertEqual(response.status_code, 302)

    def test_unknown_user_is_refused(self):
        client = self.make_app()
        self.assertEqual(self.get(client, "10.0.0.1", "stranger").status_code, 403)

    def test_misconfiguration_fails_at_start(self):
        for extra in ({"RADAR_FORWARD_AUTH_TRUSTED_PROXIES": ""}, {"RADAR_FORWARD_AUTH_TRUSTED_PROXIES": "0.0.0.0/0"},
                      {"RADAR_FORWARD_AUTH_HEADER": "Bad Header"}):
            with self.subTest(extra=extra), self.assertRaises(RuntimeError):
                self.make_app(**extra)


if __name__ == "__main__":
    unittest.main()
