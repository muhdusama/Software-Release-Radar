from __future__ import annotations

import base64
import io
import json
import os
import sqlite3
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

from radar.checker import check_all, check_tracker
from radar.db import connect, init_db, set_settings, transaction, utcnow
from radar import github as github_module
from radar.github import (GitHubError, GitHubRateLimitError, ReleaseInfo,
                          _github_get, _organizr_version_key, _persist_rate_limit, _rate_limit_retry_at,
                          _record_successful_request, get_latest,
                          get_recent_releases)
from radar.tracker_utils import is_due


class GitHubRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["RADAR_DB"] = str(Path(self.tempdir.name) / "radar.db")
        init_db()

    def tearDown(self):
        self.tempdir.cleanup()
        os.environ.pop("RADAR_DB", None)

    def _tracker(self, **overrides) -> int:
        now = utcnow()
        values = {
            "name": "Example", "repository": "owner/repo", "strategy": "release",
            "enabled": 1, "refresh_hours": 24, "current_version": "v1",
            "current_release_name": "Example v1", "created_at": now, "updated_at": now,
        }
        values.update(overrides)
        with transaction() as conn:
            return int(conn.execute(
                f"INSERT INTO trackers ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
                list(values.values()),
            ).lastrowid)

    @staticmethod
    def _http_error(code: int, body: str, headers: dict[str, str] | None = None):
        message = Message()
        for key, value in (headers or {}).items():
            message[key] = value
        return urllib.error.HTTPError("https://api.github.test", code, "error", message, io.BytesIO(body.encode()))

    def test_classifies_rate_limits_but_leaves_access_and_not_found_errors_alone(self):
        reset = int((datetime.now(timezone.utc) + timedelta(minutes=7)).timestamp())
        error = self._http_error(403, '{"message":"API rate limit exceeded"}', {"X-RateLimit-Reset": str(reset)})
        with patch("radar.github.open_http", side_effect=error):
            with self.assertRaises(GitHubRateLimitError) as caught:
                _github_get("/repos/owner/repo/releases/latest")
        self.assertGreater(caught.exception.retry_at.timestamp(), datetime.now(timezone.utc).timestamp())
        with connect() as conn:
            self.assertEqual(
                conn.execute("SELECT value FROM settings WHERE key = 'github_rate_limit_until'").fetchone()["value"],
                caught.exception.retry_at.replace(microsecond=0).isoformat(),
            )

        init_db()  # A fresh process startup retains the persisted cooldown.
        with patch("radar.github.open_http") as outbound:
            with self.assertRaises(GitHubRateLimitError) as deferred:
                _github_get("/repos/owner/repo/releases/latest")
        self.assertTrue(deferred.exception.deferred)
        outbound.assert_not_called()

        set_settings({"github_rate_limit_until": ""})
        for code, body, expected in (
            (403, '{"message":"Resource not accessible by integration"}', "access was denied"),
            (404, '{"message":"Not Found"}', "was not found"),
        ):
            with self.subTest(code=code), patch("radar.github.open_http", side_effect=self._http_error(code, body)):
                with self.assertRaises(GitHubError) as caught:
                    _github_get("/repos/owner/repo/releases/latest")
            self.assertNotIsInstance(caught.exception, GitHubRateLimitError)
            self.assertIn(expected, str(caught.exception))

    def test_honours_provider_headers_and_ignores_malformed_values(self):
        now = datetime(2026, 10, 24, 1, 0, tzinfo=timezone.utc)
        reset = int((now + timedelta(minutes=12)).timestamp())
        retry_at = _rate_limit_retry_at(
            {"Retry-After": "60", "X-RateLimit-Reset": str(reset)}, now=now,
        )
        self.assertEqual(retry_at, datetime.fromtimestamp(reset, tz=timezone.utc))
        self.assertEqual(
            _rate_limit_retry_at({"Retry-After": format_datetime(now + timedelta(minutes=3))}, now=now),
            now + timedelta(minutes=3),
        )
        self.assertIsNone(_rate_limit_retry_at({"Retry-After": "oops", "X-RateLimit-Reset": "bad"}, now=now))
        self.assertIsNone(_rate_limit_retry_at({"Retry-After": "999999999999999999999999999"}, now=now))

    def test_shared_cooldown_defers_outbound_calls_and_retries_before_normal_interval(self):
        first = self._tracker(name="First", repository="owner/first")
        second = self._tracker(name="Second", repository="owner/second")
        provider_retry = datetime.now(timezone.utc) + timedelta(minutes=5)
        with patch("radar.checker.get_latest", side_effect=GitHubRateLimitError("limited", provider_retry)):
            result = check_tracker(first, run_probe=False)
        self.assertEqual(result.status, "error")
        with connect() as conn:
            first_row = conn.execute("SELECT * FROM trackers WHERE id = ?", (first,)).fetchone()
        self.assertEqual(first_row["current_version"], "v1")
        self.assertGreaterEqual(first_row["github_retry_at"], provider_retry.replace(microsecond=0).isoformat())
        set_settings({"github_rate_limit_until": first_row["github_retry_at"]})
        self.assertGreaterEqual(first_row["github_retry_at"], provider_retry.replace(microsecond=0).isoformat())
        self.assertFalse(is_due(first_row["last_checked_at"], 24, retry_at=first_row["github_retry_at"]))
        with patch("radar.checker.get_latest") as upstream:
            deferred = check_tracker(second, run_probe=False)
        self.assertTrue(deferred.skipped)
        upstream.assert_not_called()
        self.assertEqual(check_all(enabled_only=True, due_only=True), [])

    def test_headerless_rate_limit_uses_a_persistent_minimum_backoff(self):
        tracker_id = self._tracker()
        before = datetime.now(timezone.utc)
        with patch("radar.checker.get_latest", side_effect=GitHubRateLimitError("limited")):
            check_tracker(tracker_id, run_probe=False)
        with connect() as conn:
            retry = conn.execute("SELECT github_retry_at FROM trackers WHERE id = ?", (tracker_id,)).fetchone()["github_retry_at"]
            backoff = conn.execute("SELECT value FROM settings WHERE key = 'github_rate_limit_backoff_seconds'").fetchone()["value"]
        self.assertGreaterEqual(datetime.fromisoformat(retry), before + timedelta(seconds=59))
        self.assertEqual(backoff, "120")

    def test_repeated_headerless_responses_double_and_cap_the_shared_backoff(self):
        for _ in range(8):
            with patch("radar.github.open_http", side_effect=self._http_error(429, '{"message":"slow down"}')):
                with self.assertRaises(GitHubRateLimitError):
                    _github_get("/repos/owner/repo/releases/latest")
            set_settings({"github_rate_limit_until": ""})
        with connect() as conn:
            backoff = conn.execute("SELECT value FROM settings WHERE key = 'github_rate_limit_backoff_seconds'").fetchone()["value"]
        self.assertEqual(backoff, "3600")

    def test_persisting_a_rate_limit_never_shortens_an_existing_cooldown(self):
        later = datetime.now(timezone.utc) + timedelta(minutes=10)
        earlier = datetime.now(timezone.utc) + timedelta(minutes=2)
        set_settings({"github_rate_limit_until": later.replace(microsecond=0).isoformat()})
        persisted = _persist_rate_limit(earlier)
        self.assertEqual(persisted.replace(microsecond=0), later.replace(microsecond=0))

    def test_success_clears_tracker_retry_state_after_cooldown(self):
        tracker_id = self._tracker()
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0).isoformat()
        with transaction() as conn:
            conn.execute("UPDATE trackers SET github_retry_at = ? WHERE id = ?", (past, tracker_id))
        set_settings({"github_rate_limit_until": past, "github_rate_limit_backoff_seconds": "120"})
        release = ReleaseInfo("v2", "Example v2", "https://example.test/v2", utcnow())
        with patch("radar.checker.get_latest", return_value=release):
            result = check_tracker(tracker_id, run_probe=False)
        self.assertEqual(result.status, "ok")
        with connect() as conn:
            row = conn.execute("SELECT github_retry_at, last_error FROM trackers WHERE id = ?", (tracker_id,)).fetchone()
            cooldown = conn.execute("SELECT value FROM settings WHERE key = 'github_rate_limit_until'").fetchone()["value"]
        self.assertIsNone(row["github_retry_at"])
        self.assertIsNone(row["last_error"])
        self.assertEqual(cooldown, past)

    def test_success_does_not_clear_a_newer_inflight_cooldown(self):
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(microsecond=0).isoformat()
        set_settings({"github_rate_limit_until": future, "github_rate_limit_backoff_seconds": "120"})
        _record_successful_request()
        with connect() as conn:
            cooldown = conn.execute("SELECT value FROM settings WHERE key = 'github_rate_limit_until'").fetchone()["value"]
            backoff = conn.execute("SELECT value FROM settings WHERE key = 'github_rate_limit_backoff_seconds'").fetchone()["value"]
        self.assertEqual(cooldown, future)
        self.assertEqual(backoff, "120")
        set_settings({"github_rate_limit_until": "", "github_rate_limit_backoff_seconds": "120"})
        _record_successful_request()
        with connect() as conn:
            backoff = conn.execute("SELECT value FROM settings WHERE key = 'github_rate_limit_backoff_seconds'").fetchone()["value"]
        self.assertEqual(backoff, "60")

    def test_success_cas_does_not_overwrite_a_cooldown_written_after_its_read(self):
        """The conditional clear preserves a limit reported by another request."""
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).replace(microsecond=0).isoformat()
        original_setting_value = github_module._setting_value
        replaced = False

        def interleaved_setting_value(conn, key, default=""):
            nonlocal replaced
            if key == "github_rate_limit_until" and not replaced:
                replaced = True
                conn.execute(
                    "UPDATE settings SET value = ? WHERE key = 'github_rate_limit_until'", (future,),
                )
                conn.execute(
                    "UPDATE settings SET value = '120' WHERE key = 'github_rate_limit_backoff_seconds'",
                )
                return ""
            return original_setting_value(conn, key, default)

        with patch("radar.github._setting_value", side_effect=interleaved_setting_value):
            _record_successful_request()
        with connect() as conn:
            cooldown = conn.execute("SELECT value FROM settings WHERE key = 'github_rate_limit_until'").fetchone()["value"]
            backoff = conn.execute("SELECT value FROM settings WHERE key = 'github_rate_limit_backoff_seconds'").fetchone()["value"]
        self.assertEqual(cooldown, future)
        self.assertEqual(backoff, "120")

    def test_existing_database_gains_retry_column_without_losing_cached_release(self):
        legacy_db = Path(self.tempdir.name) / "legacy.db"
        conn = sqlite3.connect(legacy_db)
        conn.executescript(
            """
            CREATE TABLE trackers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, repository TEXT NOT NULL COLLATE NOCASE UNIQUE,
                strategy TEXT NOT NULL DEFAULT 'release', include_prereleases INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1, current_version TEXT, current_release_name TEXT,
                current_release_url TEXT, current_published_at TEXT, last_checked_at TEXT,
                last_status TEXT, last_error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            INSERT INTO trackers (name, repository, current_version, current_release_name, created_at, updated_at)
            VALUES ('Legacy', 'owner/legacy', 'v1.2.3', 'Legacy v1.2.3', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
            """
        )
        conn.commit()
        conn.close()
        original = os.environ["RADAR_DB"]
        os.environ["RADAR_DB"] = str(legacy_db)
        try:
            init_db()
            init_db()
            with connect() as migrated:
                columns = {row["name"] for row in migrated.execute("PRAGMA table_info(trackers)")}
                row = migrated.execute("SELECT current_version, current_release_name, github_retry_at FROM trackers WHERE repository = 'owner/legacy'").fetchone()
            self.assertIn("github_retry_at", columns)
            self.assertEqual(row["current_version"], "v1.2.3")
            self.assertEqual(row["current_release_name"], "Legacy v1.2.3")
            self.assertIsNone(row["github_retry_at"])
        finally:
            os.environ["RADAR_DB"] = original


class OrganizrVersionFeedTests(unittest.TestCase):
    def _feed(self):
        payload = {
            "2.1.4999": {"date": "2026-01-01", "title": "Previous", "new": "One|Two"},
            "2.1.5000": {"date": "2026-02-01", "title": "Current", "fixed": "Important fix"},
            "2.1.5001-beta.2": {"date": "2026-03-01", "title": "Preview", "notes": "Preview note"},
            "2.1.5001-beta.10": {"date": "2026-03-02", "title": "Later preview", "notes": "Later preview note"},
            "2.1.5001-1": {"date": "2026-03-03", "title": "Numeric preview"},
            "2.1.5001-alpha": {"date": "2026-03-04", "title": "Alpha preview"},
        }
        return {"encoding": "base64", "content": base64.b64encode(json.dumps(payload).encode()).decode()}

    def test_organizr_uses_its_v2_version_feed_and_sorts_versions(self):
        with patch("radar.github._github_get", return_value=self._feed()) as request:
            latest = get_latest("causefx/Organizr")
            recent = get_recent_releases("causefx/Organizr", limit=2)
            prerelease = get_latest("causefx/Organizr", include_prereleases=True)
        self.assertEqual(latest.version, "2.1.5000")
        self.assertEqual(latest.name, "Current")
        self.assertIn("Fixed:\n- Important fix", latest.body)
        self.assertEqual(latest.url, "https://github.com/causefx/Organizr/blob/v2-master/js/version.json")
        self.assertEqual([release.version for release in recent], ["2.1.5000", "2.1.4999"])
        self.assertEqual(prerelease.version, "2.1.5001-beta.10")
        self.assertEqual(request.call_count, 3)

    def test_semver_numeric_prerelease_identifier_sorts_before_alphabetic_identifier(self):
        versions = ["2.1.5001-1", "2.1.5001-alpha"]
        self.assertEqual(
            sorted(versions, key=_organizr_version_key, reverse=True),
            ["2.1.5001-alpha", "2.1.5001-1"],
        )


if __name__ == "__main__":
    unittest.main()
