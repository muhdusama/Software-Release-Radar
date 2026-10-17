from pathlib import Path
import unittest


class UIReleasePolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.version = (cls.root / "VERSION").read_text().strip()
        cls.base = (cls.root / "radar" / "templates" / "base.html").read_text()
        cls.profile = (cls.root / "radar" / "templates" / "profile.html").read_text()
        cls.user_form = (cls.root / "radar" / "templates" / "user_form.html").read_text()
        cls.polish = (cls.root / "radar" / "static" / "ui-polish.css").read_text()

    def test_sidebar_version_matches_release_version(self):
        from radar.version import APP_VERSION

        self.assertEqual(APP_VERSION, self.version)
        self.assertNotIn("{% set app_version", self.base)
        self.assertIn('class="sidebar-version"', self.base)
        self.assertIn('v{{ app_version }}', self.base)
        self.assertIn("filename='ui-polish.css', v=app_version", self.base)

        previous_private_version = ".".join(("2", "6", "3"))
        self.assertNotIn(f"v='{previous_private_version}'", self.base)

    def test_account_forms_use_aligned_field_structure(self):
        for template in (self.profile, self.user_form):
            self.assertIn("account-form", template)
            self.assertIn("aligned-form-grid", template)
            self.assertIn('class="form-field"', template)
            self.assertIn('class="field-help"', template)
        self.assertIn("padding:24px 24px 0", self.polish)
        self.assertIn("grid-template-rows:auto minmax(34px,auto) auto", self.polish)
        self.assertIn("min-height:34px", self.polish)

    def test_account_inputs_have_explicit_labels(self):
        required_pairs = (
            (self.profile, "profile-username"),
            (self.profile, "profile-email"),
            (self.profile, "profile-new-password"),
            (self.profile, "profile-confirm-password"),
            (self.profile, "profile-pushover-key"),
            (self.profile, "profile-current-password"),
            (self.user_form, "user-username"),
            (self.user_form, "user-email"),
            (self.user_form, "user-role"),
            (self.user_form, "user-password"),
        )
        for template, field_id in required_pairs:
            self.assertIn(f'for="{field_id}"', template)
            self.assertIn(f'id="{field_id}"', template)


if __name__ == "__main__":
    unittest.main()
