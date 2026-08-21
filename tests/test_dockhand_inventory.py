from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from radar.auth import hash_password
from radar.db import connect, init_db, set_settings
from radar.inventory_providers import (
    DockhandProvider, InventoryProviderError, validate_origin_url,
)
from radar.manage import main as manage_main
from radar.portainer import PortainerError, import_service, sync_inventory
from radar.secrets_store import encrypt_secret


class DockhandHandler(BaseHTTPRequestHandler):
    bearer = None
    online = True
    malformed = False
    containers = []

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        type(self).bearer = self.headers.get("Authorization")
        path = self.path.split("?", 1)[0]
        if path == "/api/environments":
            self._send([{
                "id": 7, "name": "dockhand-host", "host": "192.0.2.44",
                "port": 2376, "protocol": "https",
                "connectionType": "hawser-edge",
            }])
        elif path == "/api/containers":
            self._send({"unexpected": True} if type(self).malformed else type(self).containers)
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        type(self).bearer = self.headers.get("Authorization")
        if self.path == "/api/environments/7/test":
            self._send({
                "success": type(self).online,
                "info": {"name": "dockhand-host", "containers": len(type(self).containers)},
            })
        else:
            self._send({"error": "not found"}, 404)

    def log_message(self, *args):
        pass


class DockhandInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["RADAR_DB"] = str(Path(self.tempdir.name) / "radar.db")
        os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
        os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
        os.environ["ADMIN_USERNAME"] = "admin"
        os.environ["ADMIN_EMAIL"] = "admin@example.com"
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password("correct-horse-battery")
        DockhandHandler.online = True
        DockhandHandler.malformed = False
        DockhandHandler.containers = [{
            "id": "dockhand-container-1",
            "name": "release-radar",
            "image": "ghcr.io/example/release-radar:2.7.0",
            "imageId": "sha256:image-27",
            "state": "running",
            "status": "Up 3 hours",
            "health": "healthy",
            "labels": {
                "com.docker.compose.project": "radar",
                "com.docker.compose.service": "web",
                "org.opencontainers.image.source": "https://github.com/example/release-radar",
                "org.opencontainers.image.version": "2.7.0",
            },
            "ports": [{
                "IP": "0.0.0.0", "PrivatePort": 8080,
                "PublicPort": 18080, "Type": "tcp",
            }],
        }]
        self.server = HTTPServer(("127.0.0.1", 0), DockhandHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        init_db()
        set_settings({
            "inventory_provider": "dockhand",
            "portainer_enabled": "1",
            "dockhand_base_url": f"http://127.0.0.1:{self.server.server_address[1]}",
            "dockhand_api_token_enc": encrypt_secret("dh_test_token"),
            "dockhand_verify_tls": "0",
            "dockhand_timeout": "10",
        })

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()
        for key in (
            "RADAR_DB", "SECRET_KEY", "ENCRYPTION_KEY", "ADMIN_USERNAME",
            "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH",
        ):
            os.environ.pop(key, None)

    def test_bearer_auth_and_full_normalisation(self):
        result = sync_inventory()
        self.assertTrue(result.ok)
        self.assertEqual(DockhandHandler.bearer, "Bearer dh_test_token")
        with connect() as conn:
            environment = conn.execute("SELECT * FROM portainer_environments").fetchone()
            service = conn.execute("SELECT * FROM portainer_services").fetchone()
        self.assertEqual(environment["provider"], "dockhand")
        self.assertEqual(environment["source_endpoint_id"], "7")
        self.assertEqual(environment["host"], "192.0.2.44")
        self.assertEqual(service["provider"], "dockhand")
        self.assertEqual(service["image_id"], "sha256:image-27")
        self.assertEqual(service["stack_name"], "radar")
        self.assertEqual(service["service_name"], "web")
        self.assertEqual(service["container_status"], "Up 3 hours (healthy)")
        self.assertEqual(
            json.loads(service["labels_json"])["com.docker.compose.project"],
            "radar",
        )
        self.assertEqual(service["detected_repository"], "example/release-radar")
        self.assertEqual(service["detected_version"], "2.7.0")
        self.assertEqual(service["primary_port"], 18080)
        self.assertEqual(service["health_status"], "healthy")

    def test_offline_environment_preserves_last_known_inventory(self):
        sync_inventory()
        DockhandHandler.online = False
        DockhandHandler.containers = []
        result = sync_inventory()
        self.assertEqual(result.offline_environments, 1)
        with connect() as conn:
            environment = conn.execute("SELECT status FROM portainer_environments").fetchone()
            service = conn.execute("SELECT present FROM portainer_services").fetchone()
        self.assertEqual(environment["status"], "offline")
        self.assertEqual(service["present"], 1)

    def test_online_genuinely_empty_environment_marks_previous_container_absent(self):
        sync_inventory()
        DockhandHandler.containers = []
        result = sync_inventory()
        self.assertTrue(result.ok)
        with connect() as conn:
            service = conn.execute("SELECT present FROM portainer_services").fetchone()
        self.assertEqual(service["present"], 0)

    def test_malformed_container_response_preserves_inventory_and_reports_error(self):
        sync_inventory()
        DockhandHandler.malformed = True
        result = sync_inventory()
        self.assertFalse(result.ok)
        with connect() as conn:
            service = conn.execute("SELECT present FROM portainer_services").fetchone()
            environment = conn.execute("SELECT status FROM portainer_environments").fetchone()
        self.assertEqual(service["present"], 1)
        self.assertEqual(environment["status"], "error")
        self.assertNotIn("dh_test_token", "\n".join(result.errors))

    def test_mixed_valid_and_malformed_response_preserves_inventory(self):
        sync_inventory()
        DockhandHandler.containers = [DockhandHandler.containers[0], {"name": "broken"}]
        result = sync_inventory()
        self.assertFalse(result.ok)
        with connect() as conn:
            service = conn.execute("SELECT present FROM portainer_services").fetchone()
        self.assertEqual(service["present"], 1)

    def test_tracker_rebinds_after_dockhand_container_recreation(self):
        sync_inventory()
        with connect() as conn:
            service_id = int(conn.execute("SELECT id FROM portainer_services").fetchone()["id"])
        tracker_id, _ = import_service(service_id, "example/release-radar", name="Release Radar")
        DockhandHandler.containers[0] = {
            **DockhandHandler.containers[0],
            "id": "dockhand-container-2",
        }
        sync_inventory()
        with connect() as conn:
            current = conn.execute(
                "SELECT id, tracker_id FROM portainer_services WHERE present=1"
            ).fetchone()
            tracker = conn.execute(
                "SELECT portainer_service_id, inventory_source FROM trackers WHERE id=?",
                (tracker_id,),
            ).fetchone()
        self.assertEqual(current["tracker_id"], tracker_id)
        self.assertEqual(tracker["portainer_service_id"], current["id"])
        self.assertEqual(tracker["inventory_source"], "dockhand")

    def test_normaliser_rejects_malformed_labels_and_keeps_health_and_ports(self):
        with self.assertRaises(InventoryProviderError):
            DockhandProvider.normalise_container({
                "id": "broken", "labels": [], "ports": [],
            })
        normalised = DockhandProvider.normalise_container(DockhandHandler.containers[0])
        self.assertIn("(healthy)", normalised["Status"])
        self.assertEqual(normalised["Ports"][0]["PublicPort"], 18080)

    def test_base_url_must_be_an_origin_at_save_and_request_boundaries(self):
        self.assertEqual(validate_origin_url("https://dockhand.example:8443/", "Dockhand base URL"),
                         "https://dockhand.example:8443")
        for value in (
            "https://user:secret@dockhand.example",
            "https://dockhand.example/api",
            "https://dockhand.example?token=secret",
            "https://dockhand.example#fragment",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_origin_url(value, "Dockhand base URL")
            set_settings({"dockhand_base_url": value})
            with self.assertRaises(InventoryProviderError):
                DockhandProvider().list_environments()

    def test_connection_fails_when_every_environment_is_offline(self):
        DockhandHandler.online = False
        with self.assertRaisesRegex(InventoryProviderError, "all configured.*offline"):
            DockhandProvider().test_connection()

    def test_due_sync_uses_dockhand_schedule(self):
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        set_settings({
            "inventory_provider": "dockhand",
            "dockhand_last_sync_at": now,
            "dockhand_sync_hours": "24",
            "portainer_last_sync_at": "",
            "portainer_sync_hours": "1",
        })
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = manage_main(["portainer-sync", "--due"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["action"], "skipped")
        self.assertEqual(payload["sync_hours"], 24)

    def test_derived_environment_id_collision_is_detected_without_overwrite(self):
        with connect() as conn:
            conn.execute(
                "INSERT INTO portainer_environments "
                "(endpoint_id, provider, source_endpoint_id, name, status, updated_at) "
                "VALUES (-8, 'other', 'legacy', 'Existing', 'online', '2026-08-21T00:00:00+00:00')"
            )
            conn.commit()
        with self.assertRaisesRegex(PortainerError, "identity collision"):
            sync_inventory()
        with connect() as conn:
            row = conn.execute(
                "SELECT provider, source_endpoint_id, name FROM portainer_environments WHERE endpoint_id=-8"
            ).fetchone()
        self.assertEqual((row["provider"], row["source_endpoint_id"], row["name"]),
                         ("other", "legacy", "Existing"))

    def test_existing_install_migration_is_idempotent(self):
        init_db()
        init_db()
        with connect() as conn:
            environment_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(portainer_environments)")
            }
            service_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(portainer_services)")
            }
            provider = conn.execute(
                "SELECT value FROM settings WHERE key='inventory_provider'"
            ).fetchone()["value"]
        self.assertTrue({"provider", "source_endpoint_id"}.issubset(environment_columns))
        self.assertTrue({"provider", "labels_json", "container_status"}.issubset(service_columns))
        self.assertEqual(provider, "dockhand")


if __name__ == "__main__":
    unittest.main()
