from __future__ import annotations

import unittest
from unittest.mock import patch

from radar.analysis_service import release_history_context, tracker_context
from radar.github import (GitHubError, GitHubRateLimitError, ReleaseInfo, get_latest,
                          get_recent_releases)


class SearXngRollingReleaseTests(unittest.TestCase):
    @staticmethod
    def _commit(sha: str, date: str, message: str = "Improve result handling") -> dict:
        return {"sha": sha, "commit": {"committer": {"date": date}, "message": message}}

    def test_latest_uses_master_commit_with_explicit_source_provenance(self):
        head = self._commit(
            "81371861f67226091d1c4df2e3908a11d3b54eb9", "2026-10-19T21:27:52Z",
        )
        with patch("radar.github._github_get", return_value=[head]) as request:
            release = get_latest("SearXNG/SearXNG")
        self.assertEqual(release.version, "2026.10.19-81371861f")
        self.assertEqual(release.name, "SearXNG rolling release 2026.10.19-81371861f")
        self.assertEqual(release.url, "https://github.com/searxng/searxng/commit/81371861f67226091d1c4df2e3908a11d3b54eb9")
        self.assertIn("not formal release notes", release.body)
        self.assertIn("does not prove a container image was published", release.body)
        request.assert_called_once_with("/repos/searxng/searxng/commits?sha=master&per_page=1")

    def test_history_preserves_upstream_commit_order_without_sorting_hashes(self):
        commits = [
            self._commit("f" * 40, "2026-10-20T02:00:00+10:00"),
            self._commit("0" * 40, "2026-10-19T21:27:52Z"),
            self._commit("a" * 40, "2026-10-19T20:00:00Z"),
        ]
        with patch("radar.github._github_get", return_value=commits) as request:
            releases = get_recent_releases("searxng/searxng", limit=2)
        self.assertEqual([release.version for release in releases], ["2026.10.19-fffffffff", "2026.10.19-000000000"])
        request.assert_called_once_with("/repos/searxng/searxng/commits?sha=master&per_page=2")

    def test_tag_strategy_remains_the_generic_tag_lookup(self):
        with patch("radar.github._github_get", return_value=[{"name": "v1.2.3"}]) as request:
            release = get_latest("searxng/searxng", strategy="tag")
        self.assertEqual(release.version, "v1.2.3")
        request.assert_called_once_with("/repos/searxng/searxng/tags?per_page=1")

    def test_malformed_or_empty_commit_data_fails_instead_of_using_an_older_commit(self):
        cases = (
            [],
            {"sha": "a" * 40},
            [{"sha": "short", "commit": {"committer": {"date": "2026-10-19T21:27:52Z"}}}],
            [{"sha": "a" * 40, "commit": {"committer": {"date": "2026-10-19T21:27:52"}}}],
        )
        for payload in cases:
            with self.subTest(payload=payload), patch("radar.github._github_get", return_value=payload):
                with self.assertRaisesRegex(GitHubError, "SearXNG master"):
                    get_latest("searxng/searxng")

    def test_malformed_requested_history_commit_fails_the_whole_response(self):
        payload = [
            self._commit("a" * 40, "2026-10-19T21:27:52Z"),
            {"sha": "b" * 40, "commit": {"committer": {"date": "invalid"}}},
        ]
        with patch("radar.github._github_get", return_value=payload):
            with self.assertRaisesRegex(GitHubError, "SearXNG master"):
                get_recent_releases("searxng/searxng", limit=2)

    def test_rate_limit_exception_propagates_through_the_adapter(self):
        limited = GitHubRateLimitError("scheduled")
        with patch("radar.github._github_get", side_effect=limited):
            with self.assertRaises(GitHubRateLimitError):
                get_recent_releases("searxng/searxng")

    def test_history_stays_anchored_to_cached_commit_not_a_different_same_day_commit(self):
        tracker = {
            "id": 1, "name": "SearXNG", "repository": "searxng/searxng", "strategy": "release",
            "include_prereleases": 0, "current_version": "2026.10.19-aaaaaaaaa",
            "current_release_name": "SearXNG rolling release 2026.10.19-aaaaaaaaa",
            "installed_version": "2026.10.18-ccccccccc", "detected_installed_version": None,
        }
        releases = [
            ReleaseInfo("2026.10.19-bbbbbbbbb", "SearXNG rolling release 2026.10.19-bbbbbbbbb", "", None, "wrong same-day commit"),
            ReleaseInfo("2026.10.19-aaaaaaaaa", "SearXNG rolling release 2026.10.19-aaaaaaaaa", "", None, "cached target commit"),
            ReleaseInfo("2026.10.18-ccccccccc", "SearXNG rolling release 2026.10.18-ccccccccc", "", None, "installed commit"),
        ]
        with patch("radar.analysis_service.tracker_context", return_value="Cached tracker context"):
            context = release_history_context(tracker, release_fetcher=lambda *_args, **_kwargs: releases)
        self.assertIn("upstream history", context)
        self.assertIn("cached target commit", context)
        self.assertNotIn("wrong same-day commit", context)

    def test_current_context_calls_the_cached_value_an_upstream_version(self):
        tracker = {
            "name": "SearXNG", "repository": "searxng/searxng", "installed_version": "2026.10.19-aaaaaaaaa",
            "detected_installed_version": None, "current_version": "2026.10.20-bbbbbbbbb",
            "current_release_name": "SearXNG rolling release 2026.10.20-bbbbbbbbb", "machine_name": None,
            "install_host": None, "install_scheme": None, "install_port": None, "last_probe_status": None,
            "current_release_url": None, "current_release_body": "Source commit metadata.",
        }
        with patch("radar.analysis_service._inventory_context", return_value="Inventory unavailable"):
            context = tracker_context(tracker)
        self.assertIn("Current upstream version: 2026.10.20-bbbbbbbbb", context)
        self.assertNotIn("Current Git tag", context)


if __name__ == "__main__":
    unittest.main()
