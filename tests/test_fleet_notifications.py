from __future__ import annotations

import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from radar.application import create_app
from radar.auth import hash_password, token_digest
from radar.db import connect, get_setting, set_setting, transaction, utcnow
from radar.fleet_notifications import (
    _fleet_data,
    ensure_fleet_notification_schema,
    reconcile_portainer_names,
)
from radar.notifications import dispatch_release_notifications


class FleetNotificationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "radar.db"
        os.environ["RADAR_DB"] = str(self.db)
        os.environ["SECRET_KEY"] = (
            "test-secret-key-that-is-at-least-32-bytes-long"
        )
        os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(
            os.urandom(32)
        ).decode()
        os.environ["ADMIN_USERNAME"] = "admin"
        os.environ["ADMIN_EMAIL"] = "admin@example.com"
        os.environ["ADMIN_PASSWORD_HASH"] = hash_password(
            "correct-horse-battery"
        )
        self.app = create_app()
        self.app.testing = True

    def tearDown(self):
        self.tempdir.cleanup()
        for key in (
            "RADAR_DB",
            "SECRET_KEY",
            "ENCRYPTION_KEY",
            "ADMIN_USERNAME",
            "ADMIN_EMAIL",
            "ADMIN_PASSWORD_HASH",
        ):
            os.environ.pop(key, None)

    def _portainer_tracker(self) -> int:
        now = utcnow()
        with transaction() as conn:
            conn.execute(
                """
                INSERT INTO portainer_environments
                    (endpoint_id, name, host, status, updated_at)
                VALUES (7, 'Old machine', '192.0.2.7', 'online', ?)
                """,
                (now,),
            )
            service_id = int(
                conn.execute(
                    """
                    INSERT INTO portainer_services
                        (endpoint_id, container_id, container_name, stack_name,
                         service_name, detected_version, detected_repository,
                         published_ports_json, primary_port, state, present,
                         first_seen_at, last_seen_at, updated_at)
                    VALUES (7, 'container-7', 'old-container', 'old-folder',
                            'old-service', '1.0.0', 'owner/example', '[]',
                            8080, 'running', 1, ?, ?, ?)
                    """,
                    (now, now, now),
                ).lastrowid
            )
            tracker_id = int(
                conn.execute(
                    """
                    INSERT INTO trackers
                        (name, repository, strategy, enabled, machine_name,
                         install_host, install_port, probe_mode,
                         portainer_service_id, inventory_source,
                         created_at, updated_at)
                    VALUES ('Imported old name', 'owner/example', 'release', 1,
                            'Imported old machine', '192.0.2.7', 8080,
                            'portainer', ?, 'portainer', ?, ?)
                    """,
                    (service_id, now, now),
                ).lastrowid
            )
            conn.execute(
                "UPDATE portainer_services SET tracker_id=? WHERE id=?",
                (tracker_id, service_id),
            )
        return tracker_id

    def _client(self):
        client = self.app.test_client()
        with connect() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE username='admin'"
            ).fetchone()
        with client.session_transaction() as session:
            session["user_id"] = int(user["id"])
            session["password_stamp"] = token_digest(
                str(user["password_hash"])
            )
            session["csrf_token"] = "feature-csrf"
        return client, int(user["id"])

    def test_additive_schema_is_installed(self):
        ensure_fleet_notification_schema()
        with connect() as conn:
            tracker_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(trackers)")
            }
            environment_columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(portainer_environments)"
                )
            }
            service_columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(portainer_services)"
                )
            }
            user_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(users)")
            }
            preference_table = conn.execute(
                """
                SELECT name FROM sqlite_master
                 WHERE type='table'
                   AND name='tracker_notification_preferences'
                """
            ).fetchone()
        self.assertIn("display_name_override", tracker_columns)
        self.assertIn("display_name_override", environment_columns)
        self.assertIn("stack_name_override", service_columns)
        self.assertIn("notifications_enabled", user_columns)
        self.assertIsNotNone(preference_table)
        self.assertEqual(get_setting("notifications_enabled"), "1")

    def test_portainer_renames_sync_and_local_aliases_survive(self):
        tracker_id = self._portainer_tracker()
        self.assertEqual(reconcile_portainer_names(), 1)
        with connect() as conn:
            tracker = conn.execute(
                "SELECT name, machine_name FROM trackers WHERE id=?",
                (tracker_id,),
            ).fetchone()
        self.assertEqual(tracker["name"], "old-service")
        self.assertEqual(tracker["machine_name"], "Old machine")

        with transaction() as conn:
            conn.execute(
                "UPDATE portainer_environments SET name='Renamed machine' WHERE endpoint_id=7"
            )
            conn.execute(
                """
                UPDATE portainer_services
                   SET service_name='renamed-service', stack_name='renamed-folder'
                 WHERE endpoint_id=7
                """
            )
        self.assertEqual(reconcile_portainer_names(), 1)
        with connect() as conn:
            tracker = conn.execute(
                "SELECT name, machine_name FROM trackers WHERE id=?",
                (tracker_id,),
            ).fetchone()
        self.assertEqual(tracker["name"], "renamed-service")
        self.assertEqual(tracker["machine_name"], "Renamed machine")

        with transaction() as conn:
            conn.execute(
                """
                UPDATE trackers SET display_name_override='My software'
                 WHERE id=?
                """,
                (tracker_id,),
            )
            conn.execute(
                """
                UPDATE portainer_environments
                   SET display_name_override='My machine', name='Source machine 2'
                 WHERE endpoint_id=7
                """
            )
            conn.execute(
                """
                UPDATE portainer_services
                   SET stack_name_override='My folder',
                       service_name='source-service-2',
                       stack_name='source-folder-2'
                 WHERE endpoint_id=7
                """
            )
        reconcile_portainer_names()
        machines = _fleet_data()
        tracker = machines[0]["trackers"][0]
        self.assertEqual(machines[0]["name"], "My machine")
        self.assertEqual(tracker["display_name"], "My software")
        self.assertEqual(tracker["source_display_name"], "source-service-2")
        self.assertEqual(tracker["effective_stack_name"], "My folder")
        self.assertEqual(tracker["source_stack_name"], "source-folder-2")

    def test_notification_policy_supports_global_default_and_software_override(self):
        tracker_id = self._portainer_tracker()
        ensure_fleet_notification_schema()
        now = utcnow()
        with transaction() as conn:
            user = conn.execute("SELECT * FROM users").fetchone()
            user_id = int(user["id"])
            conn.execute(
                """
                UPDATE users
                   SET notifications_enabled=0,
                       notify_email=1,
                       notify_pushover=0
                 WHERE id=?
                """,
                (user_id,),
            )
            first_event = int(
                conn.execute(
                    """
                    INSERT INTO events
                        (tracker_id, version, release_name, detected_at)
                    VALUES (?, 'v2', 'Example 2', ?)
                    """,
                    (tracker_id, now),
                ).lastrowid
            )

        with patch("radar.notifications.send_email") as send_email, patch(
            "radar.notifications.send_pushover"
        ) as send_pushover:
            counts = dispatch_release_notifications([first_event])
            self.assertEqual(counts, {"sent": 0, "failed": 0, "skipped": 2})
            send_email.assert_not_called()
            send_pushover.assert_not_called()

            with transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO tracker_notification_preferences
                        (user_id, tracker_id, mode, updated_at)
                    VALUES (?, ?, 'on', ?)
                    """,
                    (user_id, tracker_id, utcnow()),
                )
                second_event = int(
                    conn.execute(
                        """
                        INSERT INTO events
                            (tracker_id, version, release_name, detected_at)
                        VALUES (?, 'v3', 'Example 3', ?)
                        """,
                        (tracker_id, utcnow()),
                    ).lastrowid
                )
            counts = dispatch_release_notifications([second_event])
            self.assertEqual(counts, {"sent": 1, "failed": 0, "skipped": 1})
            self.assertEqual(send_email.call_count, 1)
            send_pushover.assert_not_called()

            set_setting("notifications_enabled", "0")
            with transaction() as conn:
                third_event = int(
                    conn.execute(
                        """
                        INSERT INTO events
                            (tracker_id, version, release_name, detected_at)
                        VALUES (?, 'v4', 'Example 4', ?)
                        """,
                        (tracker_id, utcnow()),
                    ).lastrowid
                )
            counts = dispatch_release_notifications([third_event])
            self.assertEqual(counts, {"sent": 0, "failed": 0, "skipped": 2})
            self.assertEqual(send_email.call_count, 1)

        with connect() as conn:
            skipped = conn.execute(
                """
                SELECT COUNT(*) FROM notification_deliveries
                 WHERE status='skipped'
                """
            ).fetchone()[0]
        self.assertEqual(skipped, 5)

    def test_fleet_and_notification_routes_save_preferences(self):
        tracker_id = self._portainer_tracker()
        client, user_id = self._client()

        fleet = client.get("/fleet")
        self.assertEqual(fleet.status_code, 200)
        body = fleet.get_data(as_text=True)
        self.assertIn("Sync names from Portainer", body)
        self.assertIn("Edit display names", body)

        renamed_machine = client.post(
            "/fleet/machines/7/name",
            data={
                "csrf_token": "feature-csrf",
                "action": "save",
                "display_name": "Production Docker host",
            },
        )
        self.assertEqual(renamed_machine.status_code, 303)

        renamed_software = client.post(
            f"/fleet/trackers/{tracker_id}/names",
            data={
                "csrf_token": "feature-csrf",
                "action": "save",
                "display_name": "Example service",
                "stack_name": "Core services",
            },
        )
        self.assertEqual(renamed_software.status_code, 303)

        defaults = client.post(
            "/notifications",
            data={
                "csrf_token": "feature-csrf",
                "action": "save_defaults",
                "system_control_present": "1",
                "system_notifications_enabled": "1",
                "notify_email": "1",
            },
        )
        self.assertEqual(defaults.status_code, 303)

        software = client.post(
            "/notifications",
            data={
                "csrf_token": "feature-csrf",
                "action": "save_software",
                f"mode_{tracker_id}": "off",
            },
        )
        self.assertEqual(software.status_code, 303)

        with connect() as conn:
            tracker = conn.execute(
                """
                SELECT name, display_name_override, machine_name
                  FROM trackers WHERE id=?
                """,
                (tracker_id,),
            ).fetchone()
            environment = conn.execute(
                """
                SELECT display_name_override
                  FROM portainer_environments WHERE endpoint_id=7
                """
            ).fetchone()
            service = conn.execute(
                """
                SELECT stack_name_override
                  FROM portainer_services WHERE endpoint_id=7
                """
            ).fetchone()
            user = conn.execute(
                "SELECT * FROM users WHERE id=?", (user_id,)
            ).fetchone()
            preference = conn.execute(
                """
                SELECT mode FROM tracker_notification_preferences
                 WHERE user_id=? AND tracker_id=?
                """,
                (user_id, tracker_id),
            ).fetchone()
        self.assertEqual(tracker["name"], "Example service")
        self.assertEqual(tracker["display_name_override"], "Example service")
        self.assertEqual(tracker["machine_name"], "Production Docker host")
        self.assertEqual(
            environment["display_name_override"], "Production Docker host"
        )
        self.assertEqual(service["stack_name_override"], "Core services")
        self.assertEqual(user["notifications_enabled"], 0)
        self.assertEqual(user["notify_email"], 1)
        self.assertEqual(user["notify_pushover"], 0)
        self.assertEqual(preference["mode"], "off")

        page = client.get("/notifications")
        self.assertEqual(page.status_code, 200)
        page_body = page.get_data(as_text=True)
        self.assertIn("Per-software controls", page_body)
        self.assertIn("Example service", page_body)
        self.assertIn("Mute", page_body)

    def test_navigation_and_styles_expose_the_new_controls(self):
        root = Path(__file__).parents[1]
        base = (root / "radar/templates/base.html").read_text()
        fleet = (root / "radar/templates/fleet.html").read_text()
        notifications = (
            root / "radar/templates/notifications.html"
        ).read_text()
        style = (root / "radar/static/ui-polish.css").read_text()
        script = (root / "radar/static/app.js").read_text()
        self.assertIn("url_for('notifications_preferences')", base)
        self.assertIn("Sync names from Portainer", fleet)
        self.assertIn("pencil-button", fleet)
        self.assertIn("Per-software controls", notifications)
        self.assertIn("system_notifications_enabled", notifications)
        self.assertIn(".inline-name-editor", style)
        self.assertIn(".software-notification-row", style)
        self.assertIn("'5': '/notifications'", script)


if __name__ == "__main__":
    unittest.main()
