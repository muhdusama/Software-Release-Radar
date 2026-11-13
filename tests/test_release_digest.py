import unittest

from radar.release_digest import advisory_ids, classify_notes, digest

NOTES = """## Breaking Changes
- Removed the legacy `--config` flag
- Node 18 is required

## Features
* Added dark mode
* Fixes a security issue in login (CVE-2026-12345)

### Upgrade notes
1. Run the database migration before starting the new version.

Deprecated: the v1 API will be removed in 3.0.
<script>alert(1)</script> [link text](https://example.invalid)
"""


class ReleaseDigestTests(unittest.TestCase):
    def test_headings_and_keywords_classify_lines(self):
        signals = classify_notes(NOTES)
        self.assertEqual(signals["breaking"], ["Removed the legacy --config flag", "Node 18 is required"])
        self.assertIn("Run the database migration before starting the new version.", signals["migration"])
        self.assertEqual(signals["security"], ["Fixes a security issue in login (CVE-2026-12345)"])
        self.assertEqual(signals["deprecation"], ["Deprecated: the v1 API will be removed in 3.0."])
        self.assertNotIn("Added dark mode", sum(signals.values(), []))

    def test_feature_names_containing_migration_are_not_upgrade_steps(self):
        signals = classify_notes("## Features\n- (migrations) Use cursor pagination for issue migration\n"
                                 "- Database migration is required for this release\n\n## Migration guide\n- Back up first")
        self.assertEqual(signals["migration"], ["Database migration is required for this release", "Back up first"])

    def test_bullet_section_labels_group_their_items(self):
        signals = classify_notes("* BREAKING\n  * Drop MySQL 5.7 (#100)\n* FEATURES\n  * Add themes\n* SECURITY\n  * Escape titles (#101)")
        self.assertEqual(signals["breaking"], ["Drop MySQL 5.7 (#100)"])
        self.assertEqual(signals["security"], ["Escape titles (#101)"])

    def test_conventional_commit_bang_marks_breaking(self):
        self.assertEqual(classify_notes("- feat(api)!: rename endpoints\n- fix: typo")["breaking"], ["feat(api)!: rename endpoints"])

    def test_markup_is_stripped_from_quoted_lines(self):
        signals = classify_notes("## Security\n- <b>Patched</b> [XSS](https://x.invalid) in `search`")
        self.assertEqual(signals["security"], ["Patched XSS in search"])

    def test_advisory_ids_are_normalised_and_unique(self):
        body = "Fixes cve-2026-0001, CVE-2026-0001 and GHSA-C2QF-rxjj-qqgw. Not GHSA-aaaa-bbbb-dddd."
        self.assertEqual(advisory_ids(body), ["CVE-2026-0001", "GHSA-c2qf-rxjj-qqgw"])

    def test_digest_totals(self):
        result = digest([{"version": "v3", "body": NOTES}, {"version": "v2", "body": "Bug fixes"}, {"version": "v1", "body": None}])
        self.assertEqual(result["totals"], {"breaking": 1, "migration": 1, "security": 1, "deprecation": 1})
        self.assertEqual(result["advisories"], ["CVE-2026-12345"])
        self.assertEqual([r["has_notes"] for r in result["releases"]], [True, True, False])


import test_mcp_auth as fixtures  # noqa: E402
from radar.db import transaction, utcnow  # noqa: E402


class ChangesPanelPageTests(unittest.TestCase):
    setUp = fixtures.MCPAuthTests.setUp
    login = fixtures.MCPAuthTests.login

    def test_panel_lists_releases_since_installed_and_escapes_notes(self):
        with transaction() as conn:
            tracker_id = conn.execute(
                "INSERT INTO trackers(name,repository,current_version,current_release_name,installed_version,last_status,created_at,updated_at)"
                " VALUES('App','o/app','v3.0.0','v3.0.0','v1.0.0','ok',?,?)", (utcnow(), utcnow())).lastrowid
            for n, body in ((1, "Initial"), (2, "## Security\n- Fix CVE-2026-1111"), (3, NOTES)):
                conn.execute("INSERT INTO events(tracker_id,version,release_name,release_body,detected_at,notified_at)"
                             " VALUES(?,?,?,?,?,?)", (tracker_id, f"v{n}.0.0", f"v{n}.0.0", body, f"2026-0{n}-01T00:00:00+00:00", utcnow()))
        self.login()
        page = self.client.get(f"/upgrades/{tracker_id}").get_data(as_text=True)
        self.assertIn("Changes since v1.0.0", page)
        self.assertIn("2 releases between your installed version and v3.0.0", page)
        self.assertIn('href="https://osv.dev/vulnerability/CVE-2026-1111"', page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("not in the stored release history", page)


if __name__ == "__main__":
    unittest.main()
