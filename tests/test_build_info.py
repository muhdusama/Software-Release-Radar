from __future__ import annotations

import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar.application import create_app
from radar.build_info import build_commit


class BuildInfoTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "RADAR_DB": str(Path(self.tempdir.name) / "radar.db"),
            "SECRET_KEY": "test-secret-key-that-is-at-least-32-bytes-long",
            "ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tempdir.cleanup()

    def test_valid_build_commit_is_normalised_and_exposed(self):
        commit = "ABCDEF1234567890ABCDEF1234567890ABCDEF12"
        with patch.dict(os.environ, {"RADAR_BUILD_COMMIT": commit}):
            self.assertEqual(build_commit(), commit.lower())
            payload = create_app().test_client().get("/healthz").get_json()

        self.assertEqual(payload["commit"], commit.lower())
        self.assertEqual(payload["status"], "ok")

    def test_invalid_build_commit_is_omitted(self):
        with patch.dict(os.environ, {"RADAR_BUILD_COMMIT": "main"}):
            self.assertIsNone(build_commit())
            payload = create_app().test_client().get("/healthz").get_json()

        self.assertNotIn("commit", payload)


if __name__ == "__main__":
    unittest.main()
