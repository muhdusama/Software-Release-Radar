from __future__ import annotations

import base64
import os
import re
import smtplib
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from radar.ai_client import AIClientError, chat as ai_chat
from radar.application import create_app
from radar.auth import hash_password
from radar.db import connect, get_setting, set_settings, transaction, utcnow
from radar.runtime_security import _BoundedResponse
from radar.safe_regex import SafeRegexError, SafeRegexTimeout, search_version
from radar.security_controls import (
    AIUsageLimitError,
    _acquire_ai_lease,
    _release_ai_lease,
)
from radar.security_policy import (
    trusted_application_origin,
    validate_credential_url,
    validate_smtp_transport,
)


class _OversizedResponse:
    def __init__(self):
        self.headers = {}

    def read(self, amount=-1):
        size = 10 if amount in (-1, None) else amount
        return b"x" * size

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class SecurityRemediationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "radar.db"
        os.environ["RADAR_DB"] = str(self.db)
        os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
        os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
        os.environ["ADMIN_USERNAME"] = "admin"
        os.environ["ADMIN_EMAIL"] = "admin@example.com"
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password("correct-horse-battery")
        os.environ["PASSWORD_RESET_MIN_SECONDS"] = "0.1"
        self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()
        for key in (
            "RADAR_DB",
            "SECRET_KEY",
            "ENCRYPTION_KEY",
            "ADMIN_USERNAME",
            "ADMIN_EMAIL",
            "ADMIN_PASSWORD_HASH",
            "PASSWORD_RESET_MIN_SECONDS",
            "ALLOW_INSECURE_INTEGRATIONS",
            "AI_USER_10_MINUTE_LIMIT",
            "AI_USER_DAILY_LIMIT",
            "AI_IP_HOURLY_LIMIT",
            "AI_USER_CONCURRENCY_LIMIT",
            "AI_GLOBAL_CONCURRENCY_LIMIT",
            "AI_REQUEST_LEASE_SECONDS",
            "AI_QUESTION_MAX_CHARS",
        ):
            os.environ.pop(key, None)

    def _csrf(self, page="/login", *, base_url: str | None = None) -> str:
        kwargs = {"base_url": base_url} if base_url else {}
        self.client.get(page, **kwargs)
        with self.client.session_transaction(**kwargs) as session:
            return str(session["csrf_token"])

    def _login(self) -> str:
        csrf = self._csrf()
        with patch("radar.web.verify_password", return_value=True):
            response = self.client.post(
                "/login",
                data={
                    "csrf_token": csrf,
                    "username": "admin",
                    "password": "correct-horse-battery",
                },
            )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            return str(session["csrf_token"])

    def _tracker(self) -> int:
        now = utcnow()
        with transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trackers
                    (name, repository, strategy, installed_version,
                     current_version, current_release_name, current_release_body,
                     created_at, updated_at)
                VALUES (?, ?, 'tag', ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Example",
                    "example/project",
                    "1.0.0",
                    "1.1.0",
                    "Example 1.1.0",
                    "Security and maintenance improvements.",
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def test_password_reset_uses_only_configured_trusted_origin(self):
        set_settings({"app_base_url": "https://radar.example.test"})
        hostile_base = "http://attacker.example"
        csrf = self._csrf("/forgot-password", base_url=hostile_base)

        with (
            patch("radar.security_controls._minimum_reset_delay"),
            patch("radar.security_controls._enqueue_email", return_value=True) as enqueue,
            patch(
                "radar.security_controls.send_email",
                side_effect=AssertionError("SMTP must not run in the request"),
            ),
        ):
            response = self.client.post(
                "/forgot-password",
                base_url=hostile_base,
                data={"csrf_token": csrf, "identity": "admin"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(enqueue.called)
        email_body = str(enqueue.call_args.args[2])
        self.assertIn("https://radar.example.test/reset-password/", email_body)
        self.assertNotIn("attacker.example", email_body)
        with connect() as conn:
            count = int(
                conn.execute("SELECT COUNT(*) FROM password_reset_tokens").fetchone()[0]
            )
        self.assertEqual(count, 1)

    def test_password_reset_does_not_fall_back_to_request_host(self):
        set_settings({"app_base_url": ""})
        hostile_base = "http://attacker.example"
        csrf = self._csrf("/forgot-password", base_url=hostile_base)

        with (
            patch("radar.security_controls._minimum_reset_delay"),
            patch("radar.security_controls._enqueue_email") as enqueue,
        ):
            response = self.client.post(
                "/forgot-password",
                base_url=hostile_base,
                data={"csrf_token": csrf, "identity": "admin"},
            )

        self.assertEqual(response.status_code, 302)
        enqueue.assert_not_called()
        with connect() as conn:
            count = int(
                conn.execute("SELECT COUNT(*) FROM password_reset_tokens").fetchone()[0]
            )
        self.assertEqual(count, 0)

    def test_trusted_application_origin_rejects_paths_and_cleartext_remote_hosts(self):
        with self.assertRaises(ValueError):
            trusted_application_origin("https://radar.example.test/subpath")
        with self.assertRaises(ValueError):
            trusted_application_origin("http://192.0.2.10")
        self.assertEqual(
            trusted_application_origin("http://127.0.0.1:9120"),
            "http://127.0.0.1:9120",
        )

    def test_assistant_question_length_is_bounded(self):
        csrf = self._login()
        tracker_id = self._tracker()
        os.environ["AI_QUESTION_MAX_CHARS"] = "250"

        with patch("radar.web.ai_chat") as provider:
            response = self.client.post(
                "/assistant/run",
                data={
                    "csrf_token": csrf,
                    "tracker_id": tracker_id,
                    "action": "chat",
                    "message": "x" * 251,
                },
            )

        self.assertEqual(response.status_code, 400)
        provider.assert_not_called()

    def test_assistant_rate_limit_is_persistent_and_per_user(self):
        csrf = self._login()
        tracker_id = self._tracker()
        os.environ["AI_USER_10_MINUTE_LIMIT"] = "1"

        with patch("radar.web.ai_chat", return_value=("Answer", "test-model")):
            first = self.client.post(
                "/assistant/run",
                data={
                    "csrf_token": csrf,
                    "tracker_id": tracker_id,
                    "action": "chat",
                    "message": "First question",
                },
            )
            second = self.client.post(
                "/assistant/run",
                data={
                    "csrf_token": csrf,
                    "tracker_id": tracker_id,
                    "action": "chat",
                    "message": "Second question",
                },
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertIn("limit", second.get_json()["error"].lower())

    def test_assistant_concurrency_lease_blocks_parallel_request(self):
        os.environ["AI_USER_CONCURRENCY_LIMIT"] = "1"
        first = _acquire_ai_lease(self.app, 1, "192.0.2.1")
        try:
            with self.assertRaises(AIUsageLimitError):
                _acquire_ai_lease(self.app, 1, "192.0.2.1")
        finally:
            _release_ai_lease(first)

    def test_recent_analysis_is_reused_without_provider_call(self):
        csrf = self._login()
        tracker_id = self._tracker()
        with connect() as conn:
            user_id = int(
                conn.execute(
                    "SELECT id FROM users WHERE username = 'admin'"
                ).fetchone()[0]
            )
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO ai_analyses
                    (tracker_id, user_id, installed_version, release_version,
                     model, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tracker_id,
                    user_id,
                    "1.0.0",
                    "1.1.0",
                    "cached-model",
                    "Cached analysis",
                    utcnow(),
                ),
            )

        with patch(
            "radar.web.ai_chat",
            side_effect=AssertionError("Provider call must be deduplicated"),
        ):
            response = self.client.post(
                "/assistant/run",
                data={
                    "csrf_token": csrf,
                    "tracker_id": tracker_id,
                    "action": "analyse",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["cached"])
        self.assertEqual(payload["answer"], "Cached analysis")

    def test_ai_client_rejects_oversized_prompt_before_network_access(self):
        with self.assertRaises(AIClientError):
            ai_chat([{"role": "user", "content": "x" * 40_001}])

    def test_credential_transport_requires_https_or_explicit_opt_in(self):
        with self.assertRaises(ValueError):
            validate_credential_url(
                "http://192.0.2.10/v1",
                credential_present=True,
                label="OpenAI-compatible base URL",
            )
        validate_credential_url(
            "http://127.0.0.1:4000/v1",
            credential_present=True,
            label="OpenAI-compatible base URL",
        )
        with self.assertRaises(ValueError):
            validate_smtp_transport(
                "smtp.example.test",
                "none",
                username_present=False,
                password_present=False,
            )

        request = urllib.request.Request(
            "http://192.0.2.10/v1",
            headers={"Authorization": "Bearer test"},
        )
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(request, timeout=0.01)

        os.environ["ALLOW_INSECURE_INTEGRATIONS"] = "true"
        validate_credential_url(
            "http://192.0.2.10/v1",
            credential_present=True,
            label="OpenAI-compatible base URL",
        )

    def test_smtp_runtime_guard_blocks_remote_cleartext_delivery(self):
        client = smtplib.SMTP()
        client._host = "smtp.example.test"
        with self.assertRaises(smtplib.SMTPException):
            client.send_message(object())

    def test_bounded_integration_response_rejects_excess_data(self):
        response = _BoundedResponse(_OversizedResponse(), 3)
        with self.assertRaises(urllib.error.URLError):
            response.read()

    def test_user_defined_regex_has_hard_size_and_time_limits(self):
        self.assertEqual(
            search_version(r"version=(\d+\.\d+\.\d+)", "version=1.2.3"),
            "1.2.3",
        )
        with self.assertRaises(SafeRegexError):
            search_version("x" * 513, "x")
        with self.assertRaises(SafeRegexTimeout):
            search_version(r"(a+)+$", ("a" * 50_000) + "!", timeout=0.05)

    def test_settings_reject_insecure_enabled_integrations(self):
        csrf = self._login()
        response = self.client.post(
            "/settings",
            data={
                "csrf_token": csrf,
                "section": "openai",
                "openai_enabled": "on",
                "openai_base_url": "http://192.0.2.10/v1",
                "openai_model": "example",
                "openai_api_key": "secret",
                "openai_timeout": "120",
                "openai_max_tokens": "1800",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_setting("openai_enabled"), "0")

    def test_github_actions_are_pinned_to_full_commit_shas(self):
        root = Path(__file__).parents[1]
        for path in (
            root / ".github/workflows/ci.yml",
            root / ".github/workflows/publish-container.yml",
        ):
            for line in path.read_text().splitlines():
                stripped = line.strip()
                if not stripped.startswith("uses:"):
                    continue
                reference = stripped.split("@", 1)[1].split()[0]
                self.assertRegex(reference, re.compile(r"^[0-9a-f]{40}$"))


if __name__ == "__main__":
    unittest.main()
