from __future__ import annotations

import base64
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from radar.ai_client import chat as ai_chat
from radar.auth import hash_password, token_digest, verify_password
from radar.checker import check_tracker
from radar.db import connect, get_setting, init_db, set_settings, transaction, utcnow
from radar.github import ReleaseInfo
from radar.manage import main as manage_main
from radar.notifications import dispatch_release_notifications
from radar.portainer import (PortainerError, import_service, inventory_summary,
                              sync_inventory, test_connection as portainer_test_connection)
from radar.portainer_jobs import enqueue_import, claim_import_job, latest_import_job
from radar.probes import _probe_ssh_docker, probe_tracker
from radar.secrets_store import decrypt_secret, encrypt_secret
from radar.versioning import classify_upgrade, versions_match
from radar.presentation import render_assistant_text
from radar.web import create_app


class VersionHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"data": {"version": "2.5.0"}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass




class AIHandler(BaseHTTPRequestHandler):
    request_payload = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        type(self).request_payload = json.loads(self.rfile.read(length).decode())
        body = json.dumps({
            "model": "litellm-test-model",
            "choices": [{"message": {"content": "Meaningful change analysis"}}],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass




class PortainerHandler(BaseHTTPRequestHandler):
    api_key = None

    def do_GET(self):
        type(self).api_key = self.headers.get("X-API-Key")
        path = self.path.split("?", 1)[0]
        if path == "/api/endpoints":
            payload = [{
                "Id": 1, "Name": "demo-host-01",
                "URL": "tcp://192.0.2.105:9001", "Type": 2,
                "Status": 1, "Platform": "Docker",
            }]
        elif path == "/api/endpoints/1/docker/containers/json":
            payload = [{
                "Id": "container-1", "Names": ["/portainer"],
                "Image": "portainer/portainer-ce:2.39.0",
                "ImageID": "sha256:image-1", "State": "running",
                "Status": "Up 2 hours (healthy)",
                "Labels": {
                    "com.docker.compose.project": "portainer",
                    "com.docker.compose.service": "portainer",
                    "org.opencontainers.image.source": "https://github.com/portainer/portainer",
                    "org.opencontainers.image.version": "2.39.0",
                },
                "Ports": [{"PrivatePort": 9443, "PublicPort": 9443, "Type": "tcp", "IP": "0.0.0.0"}],
            }]
        elif path.startswith("/api/endpoints/1/docker/images/"):
            payload = {"Config": {"Labels": {"org.opencontainers.image.version": "2.39.0"}}}
        else:
            self.send_response(404); self.end_headers(); return
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "radar.db"
        os.environ["RADAR_DB"] = str(self.db)
        os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
        os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
        os.environ["ADMIN_USERNAME"] = "admin"
        os.environ["ADMIN_EMAIL"] = "admin@example.com"
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password("correct-horse-battery")

    def tearDown(self):
        self.tempdir.cleanup()
        for key in (
            "RADAR_DB", "SECRET_KEY", "ENCRYPTION_KEY", "ADMIN_USERNAME",
            "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH",
        ):
            os.environ.pop(key, None)

    def _insert_tracker(self, **overrides) -> int:
        init_db()
        now = utcnow()
        values = {
            "name": "Example",
            "repository": "owner/repo",
            "strategy": "release",
            "include_prereleases": 0,
            "enabled": 1,
            "tags": "ai,test",
            "refresh_hours": 6,
            "current_version": "v1",
            "current_release_name": "Example v1",
            "created_at": now,
            "updated_at": now,
        }
        values.update(overrides)
        columns = ",".join(values)
        placeholders = ",".join("?" for _ in values)
        with transaction() as conn:
            return int(conn.execute(
                f"INSERT INTO trackers ({columns}) VALUES ({placeholders})",
                list(values.values()),
            ).lastrowid)

    def test_migrates_existing_1x_database_and_seeds_admin(self):
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE trackers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                repository TEXT NOT NULL COLLATE NOCASE UNIQUE,
                strategy TEXT NOT NULL DEFAULT 'release',
                include_prereleases INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                homepage_url TEXT,
                notes TEXT,
                current_version TEXT,
                current_release_name TEXT,
                current_release_url TEXT,
                current_published_at TEXT,
                last_checked_at TEXT,
                last_status TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracker_id INTEGER NOT NULL,
                version TEXT NOT NULL,
                release_name TEXT,
                release_url TEXT,
                published_at TEXT,
                detected_at TEXT NOT NULL,
                notified_at TEXT,
                UNIQUE (tracker_id, version)
            );
            """
        )
        conn.close()
        init_db()
        with connect() as conn:
            tracker_columns = {row["name"] for row in conn.execute("PRAGMA table_info(trackers)")}
            user = conn.execute("SELECT * FROM users").fetchone()
        self.assertTrue({"installed_version", "machine_name", "install_host", "probe_mode"}.issubset(tracker_columns))
        self.assertEqual(user["username"], "admin")
        self.assertEqual(user["role"], "admin")
        self.assertTrue(verify_password("correct-horse-battery", user["password_hash"]))

    def test_secret_encryption_roundtrip(self):
        encrypted = encrypt_secret("top-secret")
        self.assertNotIn("top-secret", encrypted)
        self.assertEqual(decrypt_secret(encrypted), "top-secret")

    def test_version_matching_handles_release_title_different_from_git_tag(self):
        self.assertTrue(versions_match("0.20.0", "Example App v0.20.0 (2026.8.3)", "v2026.8.3"))
        self.assertFalse(versions_match("0.19.0", "Example App v0.20.0 (2026.8.3)", "v2026.8.3"))

    def test_upgrade_classification(self):
        self.assertEqual(classify_upgrade("1.2.3", "Example v2.0.0", "v2.0.0")["level"], "major")
        self.assertEqual(classify_upgrade("1.2.3", "Example v1.3.0", "v1.3.0")["level"], "minor")
        self.assertEqual(classify_upgrade("1.2.3", "Example v1.2.4", "v1.2.4")["level"], "patch")
        self.assertEqual(classify_upgrade("1.2.3", "Example v1.2.3", "v1.2.3")["level"], "current")

    def test_records_release_body_and_transition(self):
        tracker_id = self._insert_tracker()
        release = ReleaseInfo(
            version="v2",
            name="Example 2.0",
            url="https://github.com/owner/repo/releases/tag/v2",
            published_at=utcnow(),
            body="Important migration notes",
        )
        with patch("radar.checker.get_latest", return_value=release):
            result = check_tracker(tracker_id, run_probe=False)
        self.assertTrue(result.changed)
        with connect() as conn:
            event = conn.execute("SELECT * FROM events WHERE tracker_id = ?", (tracker_id,)).fetchone()
            tracker = conn.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,)).fetchone()
        self.assertEqual(event["previous_version"], "v1")
        self.assertEqual(event["release_body"], "Important migration notes")
        self.assertEqual(tracker["current_release_body"], "Important migration notes")

    def test_http_json_probe_detects_installed_version(self):
        server = HTTPServer(("127.0.0.1", 0), VersionHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            tracker_id = self._insert_tracker(
                install_host="127.0.0.1",
                install_port=server.server_address[1],
                install_scheme="http",
                probe_mode="http_json",
                version_probe_path="/version",
                version_json_path="data.version",
            )
            result = probe_tracker(tracker_id)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.installed_version, "2.5.0")
            with connect() as conn:
                row = conn.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,)).fetchone()
            self.assertEqual(row["detected_installed_version"], "2.5.0")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_notifications_are_per_user_and_channel(self):
        tracker_id = self._insert_tracker()
        now = utcnow()
        with transaction() as conn:
            user = conn.execute("SELECT * FROM users").fetchone()
            conn.execute(
                "UPDATE users SET notify_email = 1, notify_pushover = 1, pushover_user_key_enc = ? WHERE id = ?",
                (encrypt_secret("user-key"), user["id"]),
            )
            event_id = int(conn.execute(
                "INSERT INTO events (tracker_id, version, release_name, detected_at) VALUES (?, ?, ?, ?)",
                (tracker_id, "v2", "Example 2", now),
            ).lastrowid)
        with patch("radar.notifications.send_email") as send_email, patch("radar.notifications.send_pushover") as send_pushover:
            counts = dispatch_release_notifications([event_id])
        self.assertEqual(counts["sent"], 2)
        self.assertEqual(send_email.call_count, 1)
        self.assertEqual(send_pushover.call_count, 1)
        with connect() as conn:
            deliveries = conn.execute("SELECT * FROM notification_deliveries").fetchall()
        self.assertEqual(len(deliveries), 2)

    def test_openai_compatible_chat_uses_chat_completions(self):
        init_db()
        server = HTTPServer(("127.0.0.1", 0), AIHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            set_settings({
                "openai_enabled": "1",
                "openai_base_url": f"http://127.0.0.1:{server.server_address[1]}/v1",
                "openai_api_key_enc": encrypt_secret("litellm-key"),
                "openai_model": "radar-model",
                "openai_timeout": "10",
                "openai_max_tokens": "800",
            })
            content, model = ai_chat([{"role": "user", "content": "Compare releases"}])
            self.assertEqual(content, "Meaningful change analysis")
            self.assertEqual(model, "litellm-test-model")
            self.assertEqual(AIHandler.request_payload["model"], "radar-model")
            self.assertEqual(AIHandler.request_payload["messages"][0]["content"], "Compare releases")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_ssh_docker_probe_uses_fixed_inspect_and_checks_service_port(self):
        ssh_dir = Path(self.tempdir.name) / "ssh"
        ssh_dir.mkdir()
        (ssh_dir / "id_ed25519").write_text("test")
        (ssh_dir / "known_hosts").write_text("test")
        tracker = {
            "install_host": "192.0.2.205", "install_port": 8080,
            "ssh_user": "admin", "ssh_port": 22,
            "docker_container": "open-webui", "ssh_key_name": "id_ed25519",
        }
        completed = SimpleNamespace(returncode=0, stdout="1.2.3|ghcr.io/open-webui/open-webui:1.2.3\n", stderr="")
        with patch.dict(os.environ, {"RADAR_SSH_DIR": str(ssh_dir)}), \
             patch("radar.probes._connect", return_value=7) as connect_mock, \
             patch("radar.probes.subprocess.run", return_value=completed) as run_mock:
            version, latency, source = _probe_ssh_docker(tracker)
        self.assertEqual(version, "1.2.3")
        self.assertGreaterEqual(latency, 7)
        self.assertIn("service port 8080 online", source)
        connect_mock.assert_called_once_with("192.0.2.205", 8080, timeout=4.0)
        command = run_mock.call_args.args[0]
        self.assertIn("docker inspect --format", command[-1])
        self.assertIn("open-webui", command[-1])
        self.assertNotIn("sh -c", command)

    def test_cli_manage_track_accepts_deployment_fields(self):
        release = ReleaseInfo("v3", "Example 3.0", "https://github.com/owner/repo/releases/tag/v3", utcnow(), "notes")
        output = io.StringIO()
        with patch("radar.checker.get_latest", return_value=release), redirect_stdout(output):
            code = manage_main([
                "track", "--name", "Example", "--repository", "owner/repo",
                "--refresh-hours", "12", "--tags", "AI, Self Hosted",
                "--installed-version", "v2", "--machine-name", "demo-host-01",
                "--host", "192.0.2.205", "--port", "8080",
                "--probe-mode", "manual",
            ])
        self.assertEqual(code, 0)
        self.assertIn('"action": "added"', output.getvalue())
        with connect() as conn:
            row = conn.execute("SELECT * FROM trackers").fetchone()
        self.assertEqual(row["refresh_hours"], 12)
        self.assertEqual(row["installed_version"], "v2")
        self.assertEqual(row["machine_name"], "demo-host-01")


    def test_public_compose_waits_for_radar_health_before_worker(self):
        root = Path(__file__).parents[1]
        compose = (root / "docker-compose.yml").read_text()
        self.assertIn("condition: service_healthy", compose)
        self.assertIn("http://127.0.0.1:8080/healthz", compose)
        self.assertIn("start_period: 20s", compose)
        self.assertIn("retries: 3", compose)

    def test_public_online_database_backup_uses_sqlite_backup_api(self):
        root = Path(__file__).parents[1]
        backup = (root / "scripts" / "backup.sh").read_text()
        self.assertIn("source.backup(target)", backup)
        self.assertIn("PRAGMA integrity_check", backup)
        self.assertIn('docker compose cp "radar:${CONTAINER_COPY}"', backup)
        self.assertNotIn("cp /data/radar.db", backup)

    def test_health_endpoint_uses_shared_application_version(self):
        from radar.version import APP_VERSION

        expected_version = (Path(__file__).parents[1] / "VERSION").read_text().strip()
        self.assertEqual(APP_VERSION, expected_version)
        source = (Path(__file__).parents[1] / "radar" / "web.py").read_text()
        self.assertIn('return {"status": "ok", "version": APP_VERSION', source)
        self.assertNotIn('"version": "2.0.2"', source)

    def test_cli_manage_status_and_tracker_controls(self):
        from radar.version import APP_VERSION

        tracker_id = self._insert_tracker(machine_name="demo-host-01", install_host="192.0.2.205")
        output = io.StringIO()
        with redirect_stdout(output):
            code = manage_main(["status"])
        self.assertEqual(code, 0)
        status = json.loads(output.getvalue())
        self.assertTrue(status["ok"])
        self.assertEqual(status["version"], APP_VERSION)

        for args in (
            ["pause", "--tracker-id", str(tracker_id)],
            ["resume", "--tracker-id", str(tracker_id)],
            ["refresh", "--tracker-id", str(tracker_id), "--hours", "24"],
            ["tags", "--tracker-id", str(tracker_id), "--tags", "production,critical", "--replace"],
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(manage_main(args), 0)
            self.assertTrue(json.loads(output.getvalue())["ok"])

        with connect() as conn:
            row = conn.execute("SELECT * FROM trackers WHERE id = ?", (tracker_id,)).fetchone()
        self.assertEqual(row["enabled"], 1)
        self.assertEqual(row["refresh_hours"], 24)
        self.assertEqual(row["tags"], "production,critical")

    def test_cli_manage_fleet_groups_by_machine(self):
        self._insert_tracker(machine_name="demo-host-02", install_host="192.0.2.205", installed_version="v1")
        output = io.StringIO()
        with redirect_stdout(output):
            code = manage_main(["fleet"])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["machines"][0]["machine"], "demo-host-02")
        self.assertEqual(len(payload["machines"][0]["services"]), 1)

    def test_explicit_analysis_and_chat_are_saved(self):
        tracker_id = self._insert_tracker(installed_version="v0", current_release_body="changes")
        with patch("radar.analysis_service.get_recent_releases", return_value=[]), \
             patch("radar.analysis_service.ai_chat", return_value=("Safe upgrade analysis", "litellm-model")):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(manage_main(["analyse", "--tracker-id", str(tracker_id)]), 0)
            analysis = json.loads(output.getvalue())
            self.assertTrue(analysis["ok"])
            self.assertEqual(analysis["content"], "Safe upgrade analysis")

            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(manage_main(["ask", "--tracker-id", str(tracker_id), "--question", "Should I update?"]), 0)
            answer = json.loads(output.getvalue())
            self.assertTrue(answer["ok"])
            self.assertEqual(answer["content"], "Safe upgrade analysis")

        with connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ai_analyses").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ai_conversations").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ai_messages").fetchone()[0], 2)

    def test_portainer_connection_sync_import_and_probe(self):
        init_db()
        server = HTTPServer(("127.0.0.1", 0), PortainerHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            set_settings({
                "portainer_enabled": "1",
                "portainer_base_url": f"http://127.0.0.1:{server.server_address[1]}",
                "portainer_api_token_enc": encrypt_secret("portainer-read-only"),
                "portainer_verify_tls": "0",
                "portainer_timeout": "10",
            })
            connection = portainer_test_connection()
            self.assertEqual(connection["docker_environments"], 1)
            result = sync_inventory()
            self.assertTrue(result.ok)
            self.assertEqual(result.environments, 1)
            self.assertEqual(result.services, 1)
            self.assertEqual(PortainerHandler.api_key, "portainer-read-only")
            with connect() as conn:
                service = conn.execute("SELECT * FROM portainer_services").fetchone()
            self.assertEqual(service["detected_version"], "2.39.0")
            self.assertEqual(service["detected_repository"], "portainer/portainer")
            tracker_id, action = import_service(int(service["id"]), "portainer/portainer", name="Portainer")
            self.assertEqual(action, "added")
            probe = probe_tracker(tracker_id, refresh_portainer=False)
            self.assertEqual(probe.status, "ok")
            self.assertEqual(probe.installed_version, "2.39.0")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


    def test_portainer_offline_environment_is_inventory_state_not_sync_error(self):
        init_db()
        set_settings({
            "portainer_enabled": "1",
            "portainer_base_url": "http://portainer.invalid",
            "portainer_api_token_enc": encrypt_secret("portainer-read-only"),
            "portainer_verify_tls": "0",
            "portainer_timeout": "10",
        })

        endpoint = {
            "Id": 177, "Name": "MeshCentral",
            "URL": "tcp://192.0.2.177:9001", "Type": 2,
            "Status": 1, "Platform": "Docker",
        }

        def fake_request(path, **_kwargs):
            if path == "/api/endpoints":
                return [endpoint]
            raise PortainerError(
                'Portainer API returned HTTP 502: {"message":"Proxy failure",'
                '"details":"Dial tcp 192.0.2.177:9001: connect: no route to host"}'
            )

        with patch("radar.portainer._request", side_effect=fake_request):
            result = sync_inventory()

        self.assertTrue(result.ok)
        self.assertEqual(result.offline_environments, 1)
        self.assertEqual(result.errors, [])
        summary = inventory_summary()
        self.assertEqual(summary["environment_counts"]["offline"], 1)
        self.assertEqual(summary["environment_counts"]["error"], 0)
        with connect() as conn:
            row = conn.execute(
                "SELECT status, last_seen_at FROM portainer_environments WHERE endpoint_id=177"
            ).fetchone()
            settings = conn.execute(
                "SELECT value FROM settings WHERE key='portainer_last_sync_status'"
            ).fetchone()
        self.assertEqual(row["status"], "offline")
        self.assertIsNone(row["last_seen_at"])
        self.assertEqual(settings["value"], "ok")

    def test_portainer_mixed_valid_and_malformed_response_preserves_inventory(self):
        init_db()
        set_settings({"portainer_enabled": "1", "inventory_provider": "portainer"})
        endpoint = {
            "Id": 41, "Name": "Mixed response host", "Type": 2,
            "Platform": "Docker", "URL": "tcp://192.0.2.41:9001",
        }
        valid = {
            "Id": "valid-container", "Names": ["/valid"],
            "Image": "example/valid:1.0.0", "ImageID": "sha256:valid",
            "State": "running", "Status": "Up", "Labels": {}, "Ports": [],
        }
        containers = [valid]

        def fake_request(path, **_kwargs):
            if path == "/api/endpoints":
                return [endpoint]
            if "/docker/containers/json" in path:
                return containers
            if "/docker/images/" in path:
                return {"Config": {"Labels": {}}}
            raise AssertionError(path)

        with patch("radar.portainer._request", side_effect=fake_request):
            self.assertTrue(sync_inventory().ok)
            containers[:] = [valid, {"Names": ["/missing-id"]}]
            result = sync_inventory()

        self.assertFalse(result.ok)
        with connect() as conn:
            service = conn.execute(
                "SELECT present FROM portainer_services WHERE container_id='valid-container'"
            ).fetchone()
            environment = conn.execute(
                "SELECT status FROM portainer_environments WHERE endpoint_id=41"
            ).fetchone()
        self.assertEqual(service["present"], 1)
        self.assertEqual(environment["status"], "error")

    def test_portainer_unexpected_environment_failure_remains_visible(self):
        init_db()
        set_settings({
            "portainer_enabled": "1",
            "portainer_base_url": "http://portainer.invalid",
            "portainer_api_token_enc": encrypt_secret("portainer-read-only"),
            "portainer_verify_tls": "0",
            "portainer_timeout": "10",
        })
        endpoint = {
            "Id": 2, "Name": "Protected endpoint",
            "URL": "tcp://192.0.2.2:9001", "Type": 2,
            "Status": 1, "Platform": "Docker",
        }

        def fake_request(path, **_kwargs):
            if path == "/api/endpoints":
                return [endpoint]
            raise PortainerError("Portainer API returned HTTP 403: access denied")

        with patch("radar.portainer._request", side_effect=fake_request):
            result = sync_inventory()

        self.assertFalse(result.ok)
        self.assertEqual(result.offline_environments, 0)
        self.assertEqual(len(result.errors), 1)
        summary = inventory_summary()
        self.assertEqual(summary["environment_counts"]["error"], 1)

    def test_requested_dashboard_navigation_and_filters_are_present(self):
        root = Path(__file__).parents[1]
        dashboard = (root / "radar/templates/dashboard.html").read_text()
        fleet = (root / "radar/templates/fleet.html").read_text()
        assistant = (root / "radar/templates/assistant.html").read_text()
        settings = (root / "radar/templates/settings.html").read_text()
        portainer = (root / "radar/templates/portainer.html").read_text()
        for size in (10, 25, 50, 100, 200):
            self.assertIn(f'value="{size}"', dashboard)
            self.assertIn(f'value="{size}"', portainer)
        self.assertIn('id="fleet-filter"', fleet)
        self.assertIn('id="assistant-tracker-filter"', assistant)
        self.assertIn('data-settings-target="portainer"', settings)
        self.assertIn('class="settings-shell"', settings)
        self.assertIn('class="metrics metrics-six portainer-metrics"', portainer)
        self.assertNotIn('class="metric-card"', portainer)
        self.assertIn('class="panel-header repository-header portainer-repository-header"', portainer)

    def test_settings_reject_dockhand_url_that_is_not_origin_only(self):
        init_db()
        set_settings({"dockhand_base_url": "https://dockhand.example"})
        app = create_app()
        app.testing = True
        with connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user["id"])
            session["password_stamp"] = token_digest(str(user["password_hash"]))
            session["csrf_token"] = "settings-csrf"
        response = client.post("/settings", data={
            "csrf_token": "settings-csrf", "section": "portainer",
            "inventory_provider": "dockhand", "portainer_enabled": "on",
            "portainer_base_url": "https://portainer.example",
            "portainer_timeout": "20", "portainer_sync_hours": "1",
            "portainer_verify_tls": "on",
            "dockhand_base_url": "https://dockhand.example/api?token=secret",
            "dockhand_timeout": "20", "dockhand_sync_hours": "1",
            "dockhand_verify_tls": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_setting("dockhand_base_url"), "https://dockhand.example")


    def test_portainer_sync_job_deduplicates(self):
        from radar.portainer_jobs import enqueue_sync, latest_job
        init_db()
        first, created = enqueue_sync(None)
        second, created_again = enqueue_sync(None)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first, second)
        self.assertEqual(latest_job()["status"], "queued")


    def test_portainer_import_jobs_are_deduplicated_and_claimed(self):
        init_db()
        payload = {"items": [{"service_id": 1, "repository": "owner/repo", "name": "Example"}]}
        job_id, created = enqueue_import(payload, 1)
        self.assertTrue(created)
        duplicate_id, duplicate_created = enqueue_import(payload, 1)
        self.assertFalse(duplicate_created)
        self.assertEqual(job_id, duplicate_id)
        claimed = claim_import_job("test-worker")
        self.assertEqual(claimed["id"], job_id)
        self.assertEqual(claimed["status"], "running")
        self.assertEqual(latest_import_job()["worker_id"], "test-worker")

    def test_assistant_templates_and_australian_english_are_present(self):
        root = Path(__file__).parents[1]
        assistant = (root / "radar" / "templates" / "assistant.html").read_text()
        analysis = (root / "radar" / "analysis_service.py").read_text()
        base = (root / "radar" / "templates" / "base.html").read_text()
        self.assertIn("Safe to upgrade?", assistant)
        self.assertIn("What could break?", assistant)
        self.assertIn("Pre-upgrade checklist", assistant)
        self.assertIn("Use Australian English", analysis)
        self.assertIn('lang="en-AU"', base)

    def test_flash_messages_render_as_fixed_toasts(self):
        root = Path(__file__).resolve().parents[1]
        template = (root / "radar" / "templates" / "base.html").read_text()
        css = (root / "radar" / "static" / "style.css").read_text()
        script = (root / "radar" / "static" / "app.js").read_text()
        self.assertIn('class="toast-region"', template)
        self.assertIn('id="server-flashes"', template)
        self.assertIn('.toast-region{position:fixed', css)
        self.assertIn('function notify(', script)
        self.assertNotIn('class="flash-stack"', template)

    def test_safe_assistant_rich_text_renderer_escapes_html(self):
        rendered = str(render_assistant_text("## Summary\n\n- **Safe** change\n- `<script>alert(1)</script>`"))
        self.assertIn("<h4>Summary</h4>", rendered)
        self.assertIn("<strong>Safe</strong>", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_async_assistant_route_returns_json_and_persists_chat(self):
        tracker_id = self._insert_tracker(strategy="tag", installed_version="1.0.0", current_release_body="Changes")
        app = create_app()
        app.testing = True
        with connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user["id"])
            session["password_stamp"] = token_digest(str(user["password_hash"]))
            session["csrf_token"] = "assistant-csrf"
        with patch("radar.web.ai_chat", return_value=("## Recommendation\n\n- Update now", "test-model")):
            response = client.post(
                "/assistant/run",
                data={
                    "csrf_token": "assistant-csrf",
                    "tracker_id": str(tracker_id),
                    "action": "chat",
                    "message": "Is this safe?",
                },
                headers={"Accept": "application/json", "X-Requested-With": "fetch"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["model"], "test-model")
        self.assertIn("Update now", payload["answer"])
        with connect() as conn:
            messages = conn.execute("SELECT role, content FROM ai_messages ORDER BY id").fetchall()
        self.assertEqual([(row["role"], row["content"]) for row in messages], [
            ("user", "Is this safe?"),
            ("assistant", "## Recommendation\n\n- Update now"),
        ])

    def test_global_feedback_assets_are_always_rendered(self):
        root = Path(__file__).parents[1]
        base = (root / "radar" / "templates" / "base.html").read_text()
        assistant = (root / "radar" / "templates" / "assistant.html").read_text()
        script = (root / "radar" / "static" / "app.js").read_text()
        self.assertIn('id="toast-region"', base)
        self.assertIn('id="server-flashes"', base)
        self.assertIn('data-assistant-form', assistant)
        self.assertIn('Analysing your deployment', assistant)
        self.assertIn('fetch(runUrl', script)
        self.assertIn('Assistant thinking', script)


    def test_refinement_navigation_views_and_assistant_controls_are_present(self):
        root = Path(__file__).parents[1]
        base = (root / "radar" / "templates" / "base.html").read_text()
        dashboard = (root / "radar" / "templates" / "dashboard.html").read_text()
        assistant = (root / "radar" / "templates" / "assistant.html").read_text()
        script = (root / "radar" / "static" / "app.js").read_text()
        self.assertIn('class="app-sidebar"', base)
        self.assertIn('id="command-palette"', base)
        self.assertIn('data-view-preset="updates"', dashboard)
        self.assertIn('id="saved-dashboard-view"', dashboard)
        self.assertIn("url_for('history', date=day['date'])", dashboard)
        self.assertIn('id="assistant-cancel"', assistant)
        self.assertIn('data-copy-message', assistant)
        self.assertIn('AbortController', script)
        self.assertIn('softwareReleaseRadarAssistantDraft', script)

    def test_history_filters_by_date_and_query(self):
        tracker_id = self._insert_tracker(name="Release Radar", repository="owner/release-radar")
        with transaction() as conn:
            conn.execute(
                """INSERT INTO events
                   (tracker_id, version, release_name, previous_version, detected_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (tracker_id, "v2.5.1", "Release Radar 2.5.1", "v2.5.0", "2026-08-07T00:15:00+00:00"),
            )
            conn.execute(
                """INSERT INTO events
                   (tracker_id, version, release_name, previous_version, detected_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (tracker_id, "v2.5.2", "Release Radar 2.5.2", "v2.5.1", "2026-08-08T00:15:00+00:00"),
            )
        app = create_app()
        app.testing = True
        with connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user["id"])
            session["password_stamp"] = token_digest(str(user["password_hash"]))
        response = client.get("/history?date=2026-08-07&q=2.5.1")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Release Radar 2.5.1", body)
        self.assertNotIn("Release Radar 2.5.2", body)
        invalid = client.get("/history?date=07-08-2026")
        self.assertEqual(invalid.status_code, 302)


    def test_upgrade_decision_schema_and_interface_are_present(self):
        init_db()
        with connect() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(upgrade_decisions)")}
            indexes = {row["name"] for row in conn.execute("PRAGMA index_list(upgrade_decisions)")}
        self.assertTrue({
            "tracker_id", "release_version", "decision_status", "priority", "risk",
            "maintenance_date", "checklist_json", "rollback_notes", "change_record_url",
            "previous_version", "deployed_version", "deployed_at",
        }.issubset(columns))
        self.assertTrue(any("status" in name for name in indexes))
        root = Path(__file__).parents[1]
        base = (root / "radar/templates/base.html").read_text()
        dashboard = (root / "radar/templates/dashboard.html").read_text()
        upgrades = (root / "radar/templates/upgrades.html").read_text()
        detail = (root / "radar/templates/upgrade_decision.html").read_text()
        self.assertIn("url_for('upgrades')", base)
        self.assertIn("Upgrade decision queue", dashboard)
        self.assertIn("Managed release actions".upper(), upgrades.upper())
        self.assertIn("Pre-upgrade checklist", detail)
        self.assertIn("Mark release deployed", detail)

    def test_upgrade_decision_route_saves_plan_and_records_deployment(self):
        tracker_id = self._insert_tracker(
            name="Release Radar", repository="owner/release-radar",
            installed_version="v1.0.0", current_version="v2.0.0",
            current_release_name="Release Radar v2.0.0",
            current_release_url="https://github.com/owner/release-radar/releases/tag/v2.0.0",
            machine_name="demo-host-01",
        )
        app = create_app()
        app.testing = True
        with connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user["id"])
            session["password_stamp"] = token_digest(str(user["password_hash"]))
            session["csrf_token"] = "upgrade-csrf"

        queue = client.get("/upgrades")
        self.assertEqual(queue.status_code, 200)
        self.assertIn("Release Radar v2.0.0", queue.get_data(as_text=True))

        saved = client.post(
            f"/upgrades/{tracker_id}",
            data={
                "csrf_token": "upgrade-csrf", "action": "save",
                "decision_status": "update", "priority": "high", "risk": "medium",
                "maintenance_date": "2026-08-15",
                "decision_notes": "Schedule after the database backup.",
                "change_record_url": "obsidian://open?vault=DemoVault&file=Release%20Radar",
                "checklist_items": "Back up application data\nConfirm rollback command",
                "checklist_done": ["0"],
                "rollback_notes": "Restore the prior image and database backup.",
            },
        )
        self.assertEqual(saved.status_code, 302)
        with connect() as conn:
            decision = conn.execute("SELECT * FROM upgrade_decisions WHERE tracker_id = ?", (tracker_id,)).fetchone()
        self.assertEqual(decision["decision_status"], "update")
        self.assertEqual(decision["priority"], "high")
        self.assertEqual(decision["risk"], "medium")
        self.assertEqual(decision["maintenance_date"], "2026-08-15")
        checklist = json.loads(decision["checklist_json"])
        self.assertEqual(checklist[0], {"text": "Back up application data", "done": True})
        self.assertFalse(checklist[1]["done"])

        with transaction() as conn:
            conn.execute(
                "UPDATE trackers SET detected_installed_version = 'v2.0.0', updated_at = ? WHERE id = ?",
                (utcnow(), tracker_id),
            )

        deployed = client.post(
            f"/upgrades/{tracker_id}",
            data={
                "csrf_token": "upgrade-csrf", "action": "mark_deployed",
                "decision_status": "update", "priority": "high", "risk": "medium",
                "maintenance_date": "2026-08-15",
                "decision_notes": "Validated after deployment.",
                "change_record_url": "obsidian://open?vault=DemoVault&file=Release%20Radar",
                "checklist_items": "Back up application data\nConfirm rollback command",
                "checklist_done": ["0", "1"],
                "rollback_notes": "Restore the prior image and database backup.",
            },
        )
        self.assertEqual(deployed.status_code, 302)
        with connect() as conn:
            decision = conn.execute("SELECT * FROM upgrade_decisions WHERE tracker_id = ?", (tracker_id,)).fetchone()
        self.assertEqual(decision["decision_status"], "deployed")
        self.assertEqual(decision["previous_version"], "v1.0.0")
        self.assertEqual(decision["deployed_version"], "v2.0.0")
        self.assertIsNotNone(decision["deployed_at"])

    def test_new_upstream_release_starts_a_fresh_review(self):
        tracker_id = self._insert_tracker(
            name="Example", installed_version="v1.0.0",
            current_version="v2.0.0", current_release_name="Example v2.0.0",
        )
        now = utcnow()
        with transaction() as conn:
            conn.execute(
                """INSERT INTO upgrade_decisions
                   (tracker_id, release_version, release_name, installed_version_at_decision,
                    decision_status, priority, risk, checklist_json, created_at, updated_at)
                   VALUES (?, 'v2.0.0', 'Example v2.0.0', 'v1.0.0', 'wait', 'normal', 'low', '[]', ?, ?)""",
                (tracker_id, now, now),
            )
            conn.execute(
                "UPDATE trackers SET current_version='v3.0.0', current_release_name='Example v3.0.0', updated_at=? WHERE id=?",
                (now, tracker_id),
            )
        app = create_app()
        app.testing = True
        with connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = int(user["id"])
            session["password_stamp"] = token_digest(str(user["password_hash"]))
        response = client.get("/upgrades")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Example v3.0.0", body)
        self.assertIn("Review", body)
        with connect() as conn:
            old = conn.execute("SELECT decision_status FROM upgrade_decisions WHERE tracker_id=? AND release_version='v2.0.0'", (tracker_id,)).fetchone()
            current = conn.execute("SELECT * FROM upgrade_decisions WHERE tracker_id=? AND release_version='v3.0.0'", (tracker_id,)).fetchone()
        self.assertEqual(old["decision_status"], "wait")
        self.assertIsNone(current)

    def test_cli_upgrade_commands_require_confirmation_and_persist(self):
        tracker_id = self._insert_tracker(
            installed_version="v1.0.0", current_version="v2.0.0",
            current_release_name="Example v2.0.0", machine_name="demo-host-01",
        )
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(manage_main(["upgrades"]), 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["upgrades"][0]["decision_status"], "review")

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(manage_main(["decide", "--tracker-id", str(tracker_id), "--decision", "update"]), 2)
        self.assertIn("--confirm", json.loads(output.getvalue())["error"])

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(manage_main([
                "decide", "--tracker-id", str(tracker_id), "--decision", "update",
                "--priority", "high", "--risk", "medium", "--maintenance-date", "2026-08-15",
                "--checklist-item", "Back up data", "--checklist-item", "Confirm rollback",
                "--checklist-done", "0", "--rollback-notes", "Restore backup", "--confirm",
            ]), 0)
        self.assertEqual(json.loads(output.getvalue())["decision_status"], "update")

        with transaction() as conn:
            conn.execute(
                "UPDATE trackers SET detected_installed_version = 'v2.0.0', updated_at = ? WHERE id = ?",
                (utcnow(), tracker_id),
            )
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(manage_main(["deployed", "--tracker-id", str(tracker_id), "--confirm"]), 0)
        deployed = json.loads(output.getvalue())
        self.assertEqual(deployed["previous_version"], "v1.0.0")
        self.assertEqual(deployed["deployed_version"], "v2.0.0")
        with connect() as conn:
            row = conn.execute("SELECT * FROM upgrade_decisions WHERE tracker_id=?", (tracker_id,)).fetchone()
        self.assertEqual(row["decision_status"], "deployed")


    def test_public_docker_documentation_uses_safe_first_run_flow(self):
        root = Path(__file__).resolve().parents[1]
        docs = (root / "docs" / "DOCKER.md").read_text()
        example = (root / ".env.example").read_text()
        self.assertIn("python3 scripts/bootstrap-env.py", docs)
        self.assertIn("docker compose up -d --build", docs)
        self.assertIn("./scripts/backup.sh", docs)
        self.assertIn("TRUST_PROXY_HEADERS=false", example)
        self.assertIn("SESSION_COOKIE_SECURE=false", example)
        self.assertNotIn("SECRET_KEY=change-me", example)



if __name__ == "__main__":
    unittest.main()
