from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

from radar.auth import hash_password
from radar.db import connect, init_db, set_settings, utcnow
from radar.inventory_providers import DockhandProvider, InventoryProviderError
from radar.manage import main as manage_main
from radar.portainer import rebind_inventory, sync_inventory
from radar.probes import probe_tracker


class InventoryRebindAndDockhandMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["RADAR_DB"] = str(Path(self.tempdir.name) / "radar.db")
        os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
        os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
        os.environ["ADMIN_USERNAME"] = "admin"
        os.environ["ADMIN_EMAIL"] = "admin@example.com"
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password("correct-horse-battery")
        init_db()
        set_settings({"portainer_enabled": "1", "inventory_provider": "dockhand"})

    def tearDown(self):
        self.tempdir.cleanup()
        for key in (
            "RADAR_DB", "SECRET_KEY", "ENCRYPTION_KEY", "ADMIN_USERNAME",
            "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH",
        ):
            os.environ.pop(key, None)

    def _inventory_rows(self, *, target_version: str | None = "0.89.0", target_tracker: int | None = None,
                        environment_status: str = "online"):
        now = utcnow()
        with connect() as conn:
            conn.execute(
                "INSERT INTO portainer_environments "
                "(endpoint_id, provider, source_endpoint_id, name, host, status, updated_at) "
                "VALUES (1, 'portainer', '1', 'Legacy', 'old-host', 'online', ?)", (now,)
            )
            conn.execute(
                "INSERT INTO portainer_environments "
                "(endpoint_id, provider, source_endpoint_id, name, host, status, updated_at) "
                "VALUES (-2, 'dockhand', '1', 'Dockhand', 'new-host', ?, ?)",
                (environment_status, now),
            )
            conn.execute(
                "INSERT INTO trackers "
                "(id, name, repository, strategy, include_prereleases, enabled, tags, refresh_hours, installed_version, detected_installed_version, notes, machine_name, install_host, install_port, install_scheme, probe_mode, version_probe_path, portainer_service_id, inventory_source, last_probe_status, last_probe_error, created_at, updated_at) "
                "VALUES (1, 'Manual name', 'portfolio-performance/portfolio', 'tag', 1, 0, 'manual,keep', 24, 'manual-0.80.0', '0.89.0', 'keep these notes', 'Manual host', 'manual-host', 9443, 'https', 'http_json', '/version', 10, 'portainer', 'ok', 'stale error', ?, ?)",
                (now, now),
            )
            if target_tracker is not None:
                conn.execute(
                    "INSERT INTO trackers (id, name, repository, created_at, updated_at) "
                    "VALUES (?, 'Other', 'other/repo', ?, ?)",
                    (target_tracker, now, now),
                )
            conn.execute(
                "INSERT INTO portainer_services "
                "(id, endpoint_id, provider, container_id, container_name, detected_version, state, present, ignored, first_seen_at, last_seen_at, updated_at, tracker_id) "
                "VALUES (10, 1, 'portainer', 'old-container', 'app', '0.89.0', 'running', 1, 0, ?, ?, ?, 1)",
                (now, now, now),
            )
            conn.execute(
                "INSERT INTO portainer_services "
                "(id, endpoint_id, provider, container_id, container_name, detected_version, primary_port, state, present, ignored, first_seen_at, last_seen_at, updated_at, tracker_id) "
                "VALUES (20, -2, 'dockhand', 'new-container', 'app', ?, 8080, 'running', 1, 0, ?, ?, ?, ?)",
                (target_version, now, now, now, target_tracker),
            )
            conn.execute(
                "INSERT INTO events (tracker_id, version, detected_at) VALUES (1, '0.90.0', ?)", (now,)
            )
            conn.execute(
                "INSERT INTO upgrade_decisions (tracker_id, release_version, created_at, updated_at) VALUES (1, '0.90.0', ?, ?)",
                (now, now),
            )
            conn.commit()

    def test_rebind_is_dry_run_then_preserves_tracker_preferences_and_history(self):
        self._inventory_rows()
        binding = {"tracker_id": 1, "service_id": 20, "expected_service_id": 10}

        preview = rebind_inventory([binding])
        self.assertEqual(preview["action"], "dry_run")
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT portainer_service_id FROM trackers WHERE id=1").fetchone()[0], 10)

        applied = rebind_inventory([binding], confirm=True)
        self.assertEqual(applied["action"], "rebound")
        with connect() as conn:
            tracker = conn.execute("SELECT * FROM trackers WHERE id=1").fetchone()
            old = conn.execute("SELECT tracker_id FROM portainer_services WHERE id=10").fetchone()
            target = conn.execute("SELECT tracker_id, repository_override FROM portainer_services WHERE id=20").fetchone()
            events = conn.execute("SELECT COUNT(*) FROM events WHERE tracker_id=1").fetchone()[0]
            decisions = conn.execute("SELECT COUNT(*) FROM upgrade_decisions WHERE tracker_id=1").fetchone()[0]
        self.assertEqual(tracker["portainer_service_id"], 20)
        self.assertEqual(tracker["inventory_source"], "dockhand")
        self.assertEqual(tracker["detected_installed_version"], "0.89.0")
        self.assertEqual(tracker["machine_name"], "Dockhand")
        self.assertEqual(tracker["install_host"], "new-host")
        self.assertEqual(tracker["install_port"], 8080)
        self.assertEqual(tracker["docker_container"], "app")
        self.assertEqual(tracker["probe_mode"], "portainer")
        self.assertEqual(tracker["last_probe_status"], "untested")
        self.assertIsNone(tracker["last_probe_error"])
        self.assertEqual(
            (tracker["name"], tracker["repository"], tracker["strategy"], tracker["include_prereleases"],
             tracker["enabled"], tracker["tags"], tracker["refresh_hours"], tracker["installed_version"],
             tracker["notes"], tracker["install_scheme"], tracker["version_probe_path"]),
            ("Manual name", "portfolio-performance/portfolio", "tag", 1, 0, "manual,keep", 24,
             "manual-0.80.0", "keep these notes", "https", "/version"),
        )
        self.assertIsNone(old["tracker_id"])
        self.assertEqual((target["tracker_id"], target["repository_override"]), (1, "portfolio-performance/portfolio"))
        self.assertEqual((events, decisions), (1, 1))

    def test_rebind_rejects_claimed_target_without_partial_writes(self):
        self._inventory_rows(target_tracker=2)
        with self.assertRaisesRegex(ValueError, "already assigned"):
            rebind_inventory([{"tracker_id": 1, "service_id": 20, "expected_service_id": 10}], confirm=True)
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT portainer_service_id FROM trackers WHERE id=1").fetchone()[0], 10)
            self.assertEqual(conn.execute("SELECT tracker_id FROM portainer_services WHERE id=10").fetchone()[0], 1)

    def test_rebind_validates_every_binding_before_writing_the_batch(self):
        self._inventory_rows()
        now = utcnow()
        with connect() as conn:
            conn.execute(
                "INSERT INTO trackers (id, name, repository, portainer_service_id, created_at, updated_at) "
                "VALUES (2, 'Second', 'second/repo', 30, ?, ?)", (now, now),
            )
            conn.execute(
                "INSERT INTO portainer_services "
                "(id, endpoint_id, provider, container_id, container_name, state, present, ignored, first_seen_at, last_seen_at, updated_at, tracker_id) "
                "VALUES (30, 1, 'portainer', 'old-second', 'second', 'running', 1, 0, ?, ?, ?, 2)",
                (now, now, now),
            )
            conn.execute(
                "INSERT INTO portainer_environments "
                "(endpoint_id, provider, source_endpoint_id, name, status, updated_at) "
                "VALUES (-3, 'dockhand', '2', 'Offline Dockhand', 'offline', ?)",
                (now,),
            )
            conn.execute(
                "INSERT INTO portainer_services "
                "(id, endpoint_id, provider, container_id, container_name, state, present, ignored, first_seen_at, last_seen_at, updated_at) "
                "VALUES (40, -3, 'dockhand', 'new-second', 'second', 'running', 1, 0, ?, ?, ?)",
                (now, now, now),
            )
            conn.commit()
        with self.assertRaisesRegex(ValueError, "unavailable environment"):
            rebind_inventory([
                {"tracker_id": 1, "service_id": 20, "expected_service_id": 10},
                {"tracker_id": 2, "service_id": 40, "expected_service_id": 30},
            ], confirm=True)
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT portainer_service_id FROM trackers WHERE id=1").fetchone()[0], 10)
            self.assertEqual(conn.execute("SELECT tracker_id FROM portainer_services WHERE id=10").fetchone()[0], 1)

    def test_inventory_rebind_cli_defaults_to_dry_run_without_upstream_check(self):
        self._inventory_rows()
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = manage_main([
                "inventory-rebind", "--tracker-id", "1", "--service-id", "20",
                "--expected-service-id", "10",
            ])
        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["action"], "dry_run")
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT portainer_service_id FROM trackers WHERE id=1").fetchone()[0], 10)

    def test_rebind_clears_unknown_target_detected_version_instead_of_reusing_old_container(self):
        self._inventory_rows(target_version=None)
        rebind_inventory([{"tracker_id": 1, "service_id": 20, "expected_service_id": 10}], confirm=True)
        with connect() as conn:
            tracker = conn.execute("SELECT detected_installed_version FROM trackers WHERE id=1").fetchone()
        self.assertIsNone(tracker["detected_installed_version"])

    def test_dockhand_inspects_only_legacy_label_containers_and_does_not_retain_environment(self):
        inspect_calls: list[str] = []
        containers = [
            {"id": "one", "name": "one", "image": "app:latest", "imageId": "sha256:shared", "state": "running", "labels": {"org.label-schema.version": "4.14.0"}, "ports": []},
            {"id": "two", "name": "two", "image": "app:latest", "imageId": "sha256:shared", "state": "running", "labels": {"org.label-schema.version": "4.14.0"}, "ports": []},
            {"id": "three", "name": "three", "image": "app:latest", "imageId": "sha256:three", "state": "running", "labels": {"org.label-schema.version": "4.14.0", "org.opencontainers.image.version": "1.2.3"}, "ports": []},
        ]

        def request(path, *, method="GET"):
            if path == "/api/environments":
                return [{"id": "7", "name": "Dockhand"}]
            if path == "/api/environments/7/test":
                self.assertEqual(method, "POST")
                return {"success": True}
            if path == "/api/containers?env=7&all=true":
                return containers
            if "/inspect?env=7" in path:
                container_id = path.split("/api/containers/", 1)[1].split("/inspect", 1)[0]
                inspect_calls.append(container_id)
                versions = {"one": "0.89.0", "two": "0.90.0"}
                return {"Id": container_id, "Image": "sha256:shared", "Config": {
                    "Env": [f"APP_VERSION={versions[container_id]}", "SECRET=not-retained"],
                }}
            raise AssertionError(path)

        provider = DockhandProvider(request=request)
        with patch("radar.portainer.selected_provider", return_value=provider):
            result = sync_inventory()
        self.assertTrue(result.ok)
        self.assertEqual(inspect_calls, ["one", "two"])
        with connect() as conn:
            services = conn.execute(
                "SELECT container_id, detected_version, labels_json FROM portainer_services ORDER BY container_id"
            ).fetchall()
        self.assertEqual([(row["container_id"], row["detected_version"]) for row in services], [
            ("one", "0.89.0"), ("three", "1.2.3"), ("two", "0.90.0"),
        ])
        self.assertNotIn("SECRET", "".join(row["labels_json"] for row in services))

    def test_dockhand_uses_legacy_label_when_container_inspect_is_unavailable(self):
        container = {
            "id": "legacy", "name": "legacy", "image": "app:latest", "imageId": "sha256:legacy",
            "state": "running", "labels": {"org.label-schema.version": "4.14.0"}, "ports": [],
        }

        def request(path, *, method="GET"):
            if path == "/api/environments":
                return [{"id": "7", "name": "Dockhand"}]
            if path == "/api/environments/7/test":
                return {"success": True}
            if path == "/api/containers?env=7&all=true":
                return [container]
            if "/inspect?env=7" in path:
                raise InventoryProviderError("Dockhand API returned HTTP 404: Not Found")
            raise AssertionError(path)

        with patch("radar.portainer.selected_provider", return_value=DockhandProvider(request=request)):
            self.assertTrue(sync_inventory().ok)
        with connect() as conn:
            version = conn.execute("SELECT detected_version FROM portainer_services").fetchone()[0]
        self.assertEqual(version, "4.14.0")

    def test_offline_inventory_environment_cannot_report_cached_container_healthy(self):
        self._inventory_rows(environment_status="offline")
        with connect() as conn:
            conn.execute(
                "UPDATE trackers SET inventory_source='dockhand', probe_mode='portainer', portainer_service_id=20 WHERE id=1"
            )
            conn.commit()
        result = probe_tracker(1, refresh_portainer=False)
        self.assertEqual((result.status, result.online), ("error", False))
        self.assertIn("environment is offline", result.error or "")


if __name__ == "__main__":
    unittest.main()
