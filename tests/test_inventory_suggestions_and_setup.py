from __future__ import annotations

import base64
import os
import re
import tempfile
import threading
import unittest
from pathlib import Path

from radar.application import create_app
from radar.auth import hash_password, is_valid_password_hash, setup_token, verify_password
from radar.db import connect, utcnow
from radar.known_images import normalise_image_name, suggest_repository

SECRET = "test-secret-key-that-is-at-least-32-bytes-long"
_ENV = ("RADAR_DB", "SECRET_KEY", "ENCRYPTION_KEY", "ADMIN_USERNAME", "ADMIN_EMAIL", "ADMIN_PASSWORD_HASH")


class _Base(unittest.TestCase):
    admin_hash: str | None = None

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_env = {key: os.environ.get(key) for key in _ENV}
        os.environ["RADAR_DB"] = str(Path(self.tempdir.name) / "radar.db")
        os.environ["SECRET_KEY"] = SECRET
        os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
        os.environ["ADMIN_USERNAME"] = "admin"
        os.environ.pop("ADMIN_EMAIL", None)
        if self.admin_hash is None:
            os.environ.pop("ADMIN_PASSWORD_HASH", None)
        else:
            os.environ["ADMIN_PASSWORD_HASH"] = self.admin_hash

    def tearDown(self):
        self.tempdir.cleanup()
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def make_client(self):
        app = create_app()
        app.testing = True
        return app.test_client()

    @staticmethod
    def csrf(client, path="/login") -> str:
        html = client.get(path).get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    @staticmethod
    def user_count() -> int:
        with connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


class ImageSuggestionTests(unittest.TestCase):
    def test_normalisation_strips_registry_tag_and_digest(self):
        for raw in (
            "docker.io/library/Nginx:1.27", "nginx@sha256:" + "a" * 64, "nginx:latest",
            "index.docker.io/library/nginx:1@sha256:" + "b" * 64,
        ):
            self.assertEqual(normalise_image_name(raw), "nginx", raw)
        self.assertEqual(normalise_image_name("lscr.io/linuxserver/sonarr:latest"), "linuxserver/sonarr")
        self.assertEqual(normalise_image_name("docker.io/linuxserver/sonarr"), "linuxserver/sonarr")
        self.assertEqual(normalise_image_name("registry.local:5000/team/app:2"), "registry.local:5000/team/app")

    def test_label_beats_known_image_and_source_is_reported(self):
        self.assertEqual(suggest_repository("traefik:v3", "other/fork"), ("other/fork", "image label"))
        self.assertEqual(suggest_repository("traefik:v3", None), ("traefik/traefik", "known image"))
        self.assertEqual(
            suggest_repository("ghcr.io/immich-app/immich-server:release", None),
            ("immich-app/immich", "known image"),
        )
        self.assertIsNone(suggest_repository("example/unknown:1", None))

    def test_linuxserver_packaging_label_prefers_upstream(self):
        self.assertEqual(
            suggest_repository("lscr.io/linuxserver/sonarr", "linuxserver/docker-sonarr"),
            ("Sonarr/Sonarr", "known image"),
        )
        self.assertEqual(
            suggest_repository("lscr.io/linuxserver/unlisted", "linuxserver/docker-unlisted"),
            ("linuxserver/docker-unlisted", "image label"),
        )


class BulkTrackTests(_Base):
    admin_hash = hash_password("correct-horse-battery")

    def setUp(self):
        super().setUp()
        self.client = self.make_client()
        now = utcnow()
        with connect() as conn:
            conn.execute(
                "INSERT INTO portainer_environments (endpoint_id, name, provider, host, status, updated_at)"
                " VALUES (1, 'host-a', 'portainer', '192.0.2.5', 'online', ?)", (now,))
            for cid, name, image, label in (
                ("c1", "kuma", "louislam/uptime-kuma:1", None),
                ("c2", "labelled", "example/app:2", "example/app"),
                ("c3", "mystery", "example/unknown:3", None),
            ):
                conn.execute(
                    "INSERT INTO portainer_services (endpoint_id, container_id, container_name, provider,"
                    " image, detected_version, detected_repository, first_seen_at, last_seen_at, updated_at)"
                    " VALUES (1, ?, ?, 'portainer', ?, '1.0', ?, ?, ?, ?)",
                    (cid, name, image, label, now, now, now))
            conn.commit()
        self.ids = {r["container_id"]: r["id"] for r in connect().execute("SELECT id, container_id FROM portainer_services")}

    def login(self):
        csrf = self.csrf(self.client)
        self.assertEqual(self.client.post("/login", data={
            "csrf_token": csrf, "username": "admin", "password": "correct-horse-battery"}).status_code, 302)

    def post(self, rows: dict[str, str], csrf=None):
        data = {"csrf_token": csrf if csrf is not None else self.csrf(self.client, "/portainer"),
                "refresh_hours": "6", "selected": [str(self.ids[k]) for k in rows]}
        for key, repo in rows.items():
            data[f"repository_{self.ids[key]}"] = repo
            data[f"name_{self.ids[key]}"] = key
        return self.client.post("/portainer/track-suggested", data=data)

    def test_page_lists_suggestions_with_source(self):
        self.login()
        html = self.client.get("/portainer").get_data(as_text=True)
        self.assertIn("Suggested trackers", html)
        self.assertIn("louislam/uptime-kuma", html)
        self.assertIn("known image", html)
        self.assertIn("image label", html)
        self.assertEqual(html.count('name="repository_%d"' % self.ids["c3"]), 1)  # manual list only

    def test_bulk_creates_skips_and_reports_invalid_idempotently(self):
        self.login()
        response = self.post({"c1": "louislam/uptime-kuma", "c2": "not a repo", "c3": "example/unknown"})
        self.assertEqual(response.status_code, 303)
        with connect() as conn:
            repos = {r["repository"] for r in conn.execute("SELECT repository FROM trackers")}
            bound = conn.execute("SELECT COUNT(*) FROM portainer_services WHERE tracker_id IS NOT NULL").fetchone()[0]
        self.assertEqual(repos, {"louislam/uptime-kuma", "example/unknown"})
        self.assertEqual(bound, 2)
        html = self.client.get("/portainer").get_data(as_text=True)
        self.assertIn("2 created, 0 skipped, 1 invalid", html)
        self.post({"c1": "louislam/uptime-kuma", "c2": "example/app"})
        html = self.client.get("/portainer").get_data(as_text=True)
        self.assertIn("1 created, 1 skipped, 0 invalid", html)

    def test_csrf_required_and_admin_only(self):
        self.login()
        self.assertEqual(self.post({"c1": "louislam/uptime-kuma"}, csrf="wrong").status_code, 400)
        with connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM trackers").fetchone()[0], 0)
        anonymous = self.make_client()
        self.assertEqual(anonymous.post("/portainer/track-suggested", data={}).status_code, 302)
        with connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, active, created_at, updated_at)"
                " VALUES ('viewer', ?, 'user', 1, ?, ?)", (hash_password("viewer-password-1"), utcnow(), utcnow()))
            conn.commit()
        viewer = self.make_client()
        csrf = self.csrf(viewer)
        viewer.post("/login", data={"csrf_token": csrf, "username": "viewer", "password": "viewer-password-1"})
        self.assertEqual(viewer.post("/portainer/track-suggested", data={"csrf_token": csrf}).status_code, 403)


class FirstRunSetupTests(_Base):
    def form(self, client, **overrides):
        data = {
            "csrf_token": self.csrf(client, "/setup"), "setup_token": setup_token(SECRET),
            "username": "owner", "email": "", "password": "a-long-password-1",
            "confirm_password": "a-long-password-1",
        }
        data.update(overrides)
        return data

    def test_every_page_redirects_to_setup_until_a_user_exists(self):
        client = self.make_client()
        for path in ("/", "/login", "/portainer"):
            response = client.get(path)
            self.assertEqual((response.status_code, response.headers["Location"]), (302, "/setup"), path)
        self.assertEqual(client.get("/healthz").status_code, 200)

    def test_token_is_required_and_wrong_token_is_rejected(self):
        client = self.make_client()
        self.assertEqual(client.post("/setup", data=self.form(client, setup_token="wrong")).status_code, 400)
        self.assertEqual(client.post("/setup", data=self.form(client, setup_token="")).status_code, 400)
        self.assertEqual(self.user_count(), 0)

    def test_csrf_and_password_validation(self):
        client = self.make_client()
        self.assertEqual(client.post("/setup", data=self.form(client, csrf_token="x")).status_code, 400)
        self.assertEqual(client.post("/setup", data=self.form(client, confirm_password="different")).status_code, 400)
        self.assertEqual(client.post("/setup", data=self.form(client, password="short", confirm_password="short")).status_code, 400)
        self.assertEqual(self.user_count(), 0)

    def test_successful_setup_creates_admin_logs_in_and_closes_setup(self):
        client = self.make_client()
        response = client.post("/setup", data=self.form(client))
        self.assertEqual((response.status_code, response.headers["Location"]), (302, "/"))
        with connect() as conn:
            row = conn.execute("SELECT * FROM users").fetchone()
        self.assertEqual((row["username"], row["role"], row["active"]), ("owner", "admin", 1))
        self.assertTrue(verify_password("a-long-password-1", row["password_hash"]))
        self.assertEqual(client.get("/portainer").status_code, 200)
        self.assertEqual(client.get("/setup").headers["Location"], "/login")
        other = self.make_client()
        self.assertEqual(other.get("/setup").headers["Location"], "/login")

    def test_second_submission_cannot_create_a_second_admin(self):
        first, second = self.make_client(), self.make_client()
        data_first, data_second = self.form(first), self.form(second, username="intruder")
        self.assertEqual(first.post("/setup", data=data_first).status_code, 302)
        response = second.post("/setup", data=data_second)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.user_count(), 1)

    def test_concurrent_submissions_create_exactly_one_admin(self):
        clients = [self.make_client() for _ in range(4)]
        forms = [self.form(c, username=f"owner{i}") for i, c in enumerate(clients)]
        threads = [threading.Thread(target=c.post, args=("/setup",), kwargs={"data": f})
                   for c, f in zip(clients, forms)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(self.user_count(), 1)

    def test_repeated_wrong_tokens_are_rate_limited(self):
        client = self.make_client()
        for _ in range(10):
            client.post("/setup", data=self.form(client, setup_token="wrong"))
        response = client.post("/setup", data=self.form(client))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.user_count(), 0)


class AdminHashSeedTests(_Base):
    def test_hash_validation(self):
        self.assertTrue(is_valid_password_hash(hash_password("correct-horse-battery")))
        for bad in ("", "plaintext", "bcrypt:1:abc:def", "pbkdf2_sha256:x:abc:def", "pbkdf2_sha256:1:abc:abc"):
            self.assertFalse(is_valid_password_hash(bad), bad)

    def test_invalid_hash_creates_no_admin_and_falls_back_to_setup(self):
        os.environ["ADMIN_PASSWORD_HASH"] = "$2b$12$notapbkdf2hashatallxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        with self.assertLogs("radar.db", "ERROR") as logs:
            client = self.make_client()
        self.assertIn("/setup", logs.output[0])
        self.assertEqual(self.user_count(), 0)
        self.assertEqual(client.get("/login").headers["Location"], "/setup")

    def test_valid_hash_still_seeds_admin_and_skips_setup(self):
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password("correct-horse-battery")
        client = self.make_client()
        self.assertEqual(self.user_count(), 1)
        self.assertEqual(client.get("/login").status_code, 200)
        self.assertEqual(client.get("/setup").headers["Location"], "/login")


if __name__ == "__main__":
    unittest.main()
