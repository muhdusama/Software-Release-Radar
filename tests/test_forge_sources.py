import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from radar import github
from radar.github import (GitHubError, forge_for, get_latest, get_recent_releases, normalise_repository,
                          repository_web_url)


class ForgeReferenceTests(unittest.TestCase):
    def test_hosted_forges_are_recognised_from_urls_and_paths(self):
        cases = {
            "https://gitlab.com/gitlab-org/gitlab-runner/-/releases": "gitlab.com/gitlab-org/gitlab-runner",
            "gitlab.com/group/subgroup/project": "gitlab.com/group/subgroup/project",
            "https://codeberg.org/forgejo/forgejo.git": "codeberg.org/forgejo/forgejo",
            "https://gitea.com/gitea/tea/releases": "gitea.com/gitea/tea",
            "forgejo:git.example.com/team/app": "gitea:git.example.com/team/app",
            "gitlab:gitlab.example.net/ops/tool": "gitlab:gitlab.example.net/ops/tool",
            "https://github.com/owner/repo": "owner/repo",
            "owner/repo": "owner/repo",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalise_repository(value), expected)

    def test_unknown_or_malformed_hosts_are_rejected(self):
        for value in ("https://example.com/a/b", "gitea:not a host/x/y", "gitlab.com/only-one",
                      "gitea:git.example.com/../etc", "https://user@gitlab.com/a/b"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalise_repository(value)

    def test_web_urls(self):
        self.assertEqual(repository_web_url("owner/repo"), "https://github.com/owner/repo")
        self.assertEqual(repository_web_url("gitea:git.example.com/team/app"), "https://git.example.com/team/app")
        self.assertIsNone(forge_for("owner/repo"))


class ForgeReleaseTests(unittest.TestCase):
    def test_gitlab_releases_skip_prereleases_and_map_fields(self):
        payload = [
            {"tag_name": "v2.0.0-rc1", "name": "RC", "description": "rc", "released_at": "2026-03-01T00:00:00Z"},
            {"tag_name": "v1.9.0", "name": "1.9", "description": "notes", "released_at": "2026-02-01T00:00:00Z",
             "_links": {"self": "https://gitlab.com/g/p/-/releases/v1.9.0"}},
        ]
        with patch("radar.github._forge_get", return_value=payload) as forge_get:
            release = get_latest("gitlab.com/g/p")
        self.assertEqual((release.version, release.body, release.url),
                         ("v1.9.0", "notes", "https://gitlab.com/g/p/-/releases/v1.9.0"))
        self.assertIn("/api/v4/projects/g%2Fp/releases", forge_get.call_args.args[1])

    def test_gitea_releases_use_flags_and_ignore_github_cooldown(self):
        payload = [{"tag_name": "v3", "prerelease": True}, {"tag_name": "v2", "draft": True},
                   {"tag_name": "v1", "name": "One", "body": "b", "published_at": "2026-01-01T00:00:00Z",
                    "html_url": "https://codeberg.org/o/r/releases/tag/v1"}]
        with patch("radar.github._forge_get", return_value=payload) as forge_get, \
             patch("radar.github._github_get", side_effect=AssertionError("GitHub must not be called")):
            releases = get_recent_releases("codeberg.org/o/r", limit=10)
            with_pre = get_recent_releases("codeberg.org/o/r", include_prereleases=True, limit=10)
        self.assertEqual([r.version for r in releases], ["v1"])
        self.assertEqual([r.version for r in with_pre], ["v3", "v1"])
        self.assertEqual(forge_get.call_args.args[1], "/api/v1/repos/o/r/releases?limit=50&page=1")

    def test_latest_is_the_highest_version_not_the_newest_backport(self):
        payload = [{"tag_name": "v19.3.6", "released_at": "2026-11-06T00:00:00Z"},
                   {"tag_name": "v19.5.3", "released_at": "2026-11-01T00:00:00Z"},
                   {"tag_name": "v19.4.4", "released_at": "2026-11-02T00:00:00Z"}]
        with patch("radar.github._forge_get", return_value=payload):
            self.assertEqual(get_latest("gitlab.com/g/p").version, "v19.5.3")

    def test_forge_errors_are_reported_as_upstream_errors(self):
        with patch("radar.github._forge_get", return_value={"message": "nope"}), self.assertRaises(GitHubError):
            get_latest("codeberg.org/o/r")


class GitHubPaginationTests(unittest.TestCase):
    @staticmethod
    def page(start, count):
        return [{"tag_name": f"v{n}", "name": f"v{n}", "published_at": "2026-01-01T00:00:00Z"}
                for n in range(start, start - count, -1)]

    def test_history_pages_until_the_installed_release_is_found(self):
        pages = [self.page(300, 100), self.page(200, 100), self.page(100, 100)]
        with patch("radar.github._github_get", side_effect=pages) as github_get:
            releases = get_recent_releases("owner/repo", limit=300, stop_when=lambda r: r.version == "v150")
        self.assertEqual(github_get.call_count, 2)
        self.assertEqual(len(releases), 200)
        self.assertIn("per_page=100&page=2", github_get.call_args.args[0])

    def test_small_limits_make_one_request(self):
        with patch("radar.github._github_get", return_value=self.page(30, 20)) as github_get:
            self.assertEqual(len(get_recent_releases("owner/repo", limit=20)), 20)
        github_get.assert_called_once_with("/repos/owner/repo/releases?per_page=20")


class ForgeCheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"RADAR_DB": str(Path(self.tmp.name) / "radar.db")})
        env.start()
        self.addCleanup(env.stop)
        from radar.db import init_db, transaction, utcnow
        init_db()
        with transaction() as conn:
            conn.execute("INSERT INTO trackers(name,repository,strategy,created_at,updated_at) VALUES('Forgejo','codeberg.org/forgejo/forgejo','tag',?,?)",
                         (utcnow(), utcnow()))
            github._set_setting(conn, github._RATE_LIMIT_UNTIL,
                                (datetime.now(timezone.utc) + timedelta(hours=1)).replace(microsecond=0).isoformat())

    def test_github_cooldown_does_not_defer_forge_trackers(self):
        from radar.checker import check_all
        with patch("radar.checker.get_latest", return_value=github.ReleaseInfo("v9", "v9", None, None)):
            results = check_all(due_only=True)
        self.assertEqual([(r.status, r.version) for r in results], [("ok", "v9")])


if __name__ == "__main__":
    unittest.main()
