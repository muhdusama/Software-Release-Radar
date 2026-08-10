import sqlite3
import unittest

from radar.portainer import _canonicalise_service_tracker_link


def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE trackers ("
        "id INTEGER PRIMARY KEY, "
        "repository TEXT NOT NULL COLLATE NOCASE UNIQUE, "
        "portainer_service_id INTEGER"
        ");"
        "CREATE TABLE portainer_services ("
        "id INTEGER PRIMARY KEY, "
        "endpoint_id INTEGER NOT NULL, "
        "container_name TEXT NOT NULL, "
        "present INTEGER NOT NULL, "
        "tracker_id INTEGER, "
        "updated_at TEXT"
        ");"
    )
    return conn


class PortainerRebindV263Tests(unittest.TestCase):
    def test_rebinds_recreated_container_on_same_endpoint_name_and_repository(self):
        conn = connection()
        conn.execute("INSERT INTO trackers VALUES (1, 'gotify/server', 10)")
        conn.execute("INSERT INTO portainer_services VALUES (10,97,'gotify',0,1,'old')")
        conn.execute("INSERT INTO portainer_services VALUES (11,97,'gotify',1,NULL,'new')")
        service = conn.execute("SELECT * FROM portainer_services WHERE id=11").fetchone()

        result = _canonicalise_service_tracker_link(
            conn, service, "gotify/server",
            endpoint_id=97, container_name="gotify", now="now",
        )

        self.assertEqual(result["tracker_id"], 1)
        self.assertIsNone(
            conn.execute(
                "SELECT tracker_id FROM portainer_services WHERE id=10"
            ).fetchone()["tracker_id"]
        )

    def test_does_not_rebind_across_portainer_endpoints(self):
        conn = connection()
        conn.execute("INSERT INTO trackers VALUES (1, 'gotify/server', 10)")
        conn.execute("INSERT INTO portainer_services VALUES (10,97,'gotify',0,1,'old')")
        conn.execute("INSERT INTO portainer_services VALUES (11,1,'gotify',1,NULL,'new')")
        service = conn.execute("SELECT * FROM portainer_services WHERE id=11").fetchone()

        result = _canonicalise_service_tracker_link(
            conn, service, "gotify/server",
            endpoint_id=1, container_name="gotify", now="now",
        )

        self.assertIsNone(result["tracker_id"])

    def test_does_not_rebind_when_container_name_changes(self):
        conn = connection()
        conn.execute("INSERT INTO trackers VALUES (1, 'jc21/nginx-proxy-manager', 10)")
        conn.execute("INSERT INTO portainer_services VALUES (10,97,'nginx',0,1,'old')")
        conn.execute("INSERT INTO portainer_services VALUES (11,97,'npm',1,NULL,'new')")
        service = conn.execute("SELECT * FROM portainer_services WHERE id=11").fetchone()

        result = _canonicalise_service_tracker_link(
            conn, service, "jc21/nginx-proxy-manager",
            endpoint_id=97, container_name="npm", now="now",
        )

        self.assertIsNone(result["tracker_id"])

    def test_canonical_current_mapping_prevents_duplicate_service_steal(self):
        conn = connection()
        conn.execute("INSERT INTO trackers VALUES (1, 'immich-app/immich', 10)")
        conn.execute("INSERT INTO portainer_services VALUES (10,70,'immich_server',1,1,'old')")
        conn.execute("INSERT INTO portainer_services VALUES (11,70,'immich_machine_learning',1,1,'new')")
        service = conn.execute("SELECT * FROM portainer_services WHERE id=11").fetchone()

        result = _canonicalise_service_tracker_link(
            conn, service, "immich-app/immich",
            endpoint_id=70, container_name="immich_machine_learning", now="now",
        )

        self.assertIsNone(result["tracker_id"])
        self.assertEqual(
            conn.execute(
                "SELECT tracker_id FROM portainer_services WHERE id=10"
            ).fetchone()["tracker_id"],
            1,
        )

    def test_unmapped_tracker_keeps_existing_exact_repository_auto_link(self):
        conn = connection()
        conn.execute("INSERT INTO trackers VALUES (1, 'portainer/portainer', NULL)")
        conn.execute("INSERT INTO portainer_services VALUES (11,97,'portainer',1,NULL,'new')")
        service = conn.execute("SELECT * FROM portainer_services WHERE id=11").fetchone()

        result = _canonicalise_service_tracker_link(
            conn, service, "portainer/portainer",
            endpoint_id=97, container_name="portainer", now="now",
        )

        self.assertEqual(result["tracker_id"], 1)


    def test_explicit_mapping_stays_authoritative_during_sync_present_reset(self):
        conn = connection()
        conn.execute("INSERT INTO trackers VALUES (1, 'immich-app/immich', 10)")
        conn.execute("INSERT INTO portainer_services VALUES (10,70,'immich_machine_learning',0,1,'old')")
        conn.execute("INSERT INTO portainer_services VALUES (11,70,'immich_server',1,1,'new')")
        service = conn.execute("SELECT * FROM portainer_services WHERE id=11").fetchone()

        result = _canonicalise_service_tracker_link(
            conn, service, "immich-app/immich",
            endpoint_id=70, container_name="immich_server", now="now",
        )

        self.assertIsNone(result["tracker_id"])
        self.assertEqual(
            conn.execute("SELECT tracker_id FROM portainer_services WHERE id=10").fetchone()["tracker_id"],
            1,
        )
        self.assertEqual(
            conn.execute("SELECT portainer_service_id FROM trackers WHERE id=1").fetchone()["portainer_service_id"],
            10,
        )



if __name__ == "__main__":
    unittest.main()
