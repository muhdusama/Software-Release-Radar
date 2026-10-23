from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar.auth import hash_password
from radar.db import connect, init_db, set_settings
from radar.inventory_providers import DockhandProvider, InventoryEnvironment
from radar.portainer import (
    _image_metadata, _repository_from, _version_from, sync_inventory,
)


class ImageVersionMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["RADAR_DB"] = str(Path(self.tempdir.name) / "radar.db")
        os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
        os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
        os.environ["ADMIN_USERNAME"] = "admin"
        os.environ["ADMIN_EMAIL"] = "admin@example.com"
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password("correct-horse-battery")
        init_db()
        set_settings({"portainer_enabled": "1", "inventory_provider": "portainer"})

    def tearDown(self):
        self.tempdir.cleanup()
        for key in (
            "RADAR_DB", "SECRET_KEY", "ENCRYPTION_KEY", "ADMIN_USERNAME",
            "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH",
        ):
            os.environ.pop(key, None)

    def test_inspect_app_version_beats_inherited_legacy_label_without_storing_env(self):
        inspect_calls = 0
        endpoint = {"Id": 1, "Name": "host", "Type": 2, "Platform": "Docker"}
        container = {
            "Id": "portfolio", "Names": ["/portfolio"],
            "Image": "meronx/portfolio-performance:latest", "ImageID": "sha256:portfolio",
            "State": "running", "Status": "Up", "Labels": {
                "org.opencontainers.image.source": "MERONX/PORTFOLIO-PERFORMANCE",
            }, "Ports": [],
        }

        def request(path, **_kwargs):
            nonlocal inspect_calls
            if path == "/api/endpoints":
                return [endpoint]
            if "/docker/containers/json" in path:
                return [container]
            if "/docker/images/" in path:
                inspect_calls += 1
                return {"Config": {
                    "Labels": {"org.label-schema.version": "4.14.0"},
                    "Env": [
                        "APP_NAME=Portfolio Performance", "APP_VERSION=0.89.0",
                        "DOCKER_IMAGE_VERSION=0.89.0", "UNRELATED_SECRET=must-not-persist",
                    ],
                }}
            raise AssertionError(path)

        with patch("radar.portainer._request", side_effect=request):
            result = sync_inventory()

        self.assertTrue(result.ok)
        self.assertEqual(inspect_calls, 1)
        with connect() as conn:
            service = conn.execute("SELECT * FROM portainer_services").fetchone()
        self.assertEqual(service["detected_version"], "0.89.0")
        self.assertEqual(service["detected_repository"], "portfolio-performance/portfolio")
        self.assertEqual(json.loads(service["labels_json"]), {
            "org.label-schema.version": "4.14.0",
            "org.opencontainers.image.source": "MERONX/PORTFOLIO-PERFORMANCE",
        })

    def test_explicit_labels_win_then_invalid_or_missing_app_version_uses_legacy_label(self):
        labels = {
            "software-release-radar.version": "9.0.0",
            "org.opencontainers.image.version": "8.0.0",
            "org.label-schema.version": "4.14.0",
        }
        self.assertEqual(_version_from("example/app:latest", labels, "0.89.0"), "9.0.0")
        self.assertEqual(
            _version_from("example/app:latest", {
                "software.release.radar.version": "8.5.0",
                "org.opencontainers.image.version": "8.0.0",
            }, "0.89.0"),
            "8.5.0",
        )
        self.assertEqual(
            _version_from("example/app:latest", {"org.label-schema.version": "4.14.0"}, None),
            "4.14.0",
        )

        with patch("radar.portainer._request", return_value={"Config": {
            "Labels": {"org.label-schema.version": "4.14.0"},
            "Env": ["APP_VERSION=not-a-version", "DOCKER_IMAGE_VERSION=0.89.0"],
        }}):
            labels, app_version = _image_metadata(1, "sha256:portfolio")
        self.assertEqual(labels, {"org.label-schema.version": "4.14.0"})
        self.assertIsNone(app_version)
        self.assertEqual(_version_from("example/app:latest", labels, app_version), "4.14.0")

    def test_source_aliases_are_limited_to_image_source_labels_and_explicit_override_wins(self):
        self.assertEqual(
            _repository_from({"org.opencontainers.image.source": "ORGANIZR/docker-organizr"}),
            "causefx/Organizr",
        )
        self.assertEqual(
            _repository_from({"org.label-schema.vcs-url": "meronx/portfolio-performance"}),
            "portfolio-performance/portfolio",
        )
        self.assertEqual(
            _repository_from({
                "software-release-radar.repository": "custom/portfolio",
                "org.opencontainers.image.source": "meronx/portfolio-performance",
            }),
            "custom/portfolio",
        )

    def test_provider_without_image_inspection_keeps_label_only_behaviour(self):
        environment = InventoryEnvironment(source_id="7", name="dockhand")
        self.assertEqual(DockhandProvider().image_metadata(environment, "sha256:example"), ({}, None))


if __name__ == "__main__":
    unittest.main()
