from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from flask import Flask

from radar.build_info import build_commit, install_build_metadata


def _test_app() -> Flask:
    app = Flask(__name__)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "version": "test", "name": "Software Release Radar"}

    install_build_metadata(app)
    return app


class BuildInfoTests(unittest.TestCase):
    def test_valid_build_commit_is_normalised_and_exposed(self):
        commit = "ABCDEF1234567890ABCDEF1234567890ABCDEF12"
        with patch.dict(os.environ, {"RADAR_BUILD_COMMIT": commit}, clear=False):
            self.assertEqual(build_commit(), commit.lower())
            payload = _test_app().test_client().get("/healthz").get_json()

        self.assertEqual(payload["commit"], commit.lower())
        self.assertEqual(payload["status"], "ok")

    def test_invalid_build_commit_is_omitted(self):
        with patch.dict(os.environ, {"RADAR_BUILD_COMMIT": "main"}, clear=False):
            self.assertIsNone(build_commit())
            payload = _test_app().test_client().get("/healthz").get_json()

        self.assertNotIn("commit", payload)


if __name__ == "__main__":
    unittest.main()
