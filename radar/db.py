from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

DEFAULT_REFRESH_HOURS = 6
ALLOWED_REFRESH_HOURS = (1, 2, 3, 6, 12, 24, 48, 72, 168)


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def db_path() -> Path:
    return Path(os.environ.get("RADAR_DB", "/data/radar.db"))


class ClosingConnection(sqlite3.Connection):
    """SQLite connection whose ``with`` block also closes the handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _seed_admin(conn: sqlite3.Connection) -> None:
    count = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    if count:
        return
    username = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "").strip()
    email = os.environ.get("ADMIN_EMAIL", "").strip() or None
    if not password_hash:
        return
    now = utcnow()
    conn.execute(
        """
        INSERT INTO users
            (username, email, password_hash, role, active, notify_email,
             notify_pushover, pushover_user_key_enc, created_at, updated_at)
        VALUES (?, ?, ?, 'admin', 1, 1, 0, '', ?, ?)
        """,
        (username, email, password_hash, now, now),
    )


def init_db() -> None:
    with transaction() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS trackers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                repository TEXT NOT NULL COLLATE NOCASE UNIQUE,
                strategy TEXT NOT NULL DEFAULT 'release'
                    CHECK (strategy IN ('release', 'tag')),
                include_prereleases INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                homepage_url TEXT,
                notes TEXT,
                tags TEXT NOT NULL DEFAULT '',
                refresh_hours INTEGER NOT NULL DEFAULT 6,
                current_version TEXT,
                current_release_name TEXT,
                current_release_url TEXT,
                current_release_body TEXT,
                current_published_at TEXT,
                installed_version TEXT,
                detected_installed_version TEXT,
                machine_name TEXT,
                install_host TEXT,
                install_port INTEGER,
                install_scheme TEXT NOT NULL DEFAULT 'http',
                health_path TEXT NOT NULL DEFAULT '/',
                probe_mode TEXT NOT NULL DEFAULT 'manual',
                version_probe_path TEXT,
                version_json_path TEXT,
                version_regex TEXT,
                ssh_user TEXT,
                ssh_port INTEGER NOT NULL DEFAULT 22,
                docker_container TEXT,
                ssh_key_name TEXT,
                last_probe_at TEXT,
                last_probe_status TEXT,
                last_probe_error TEXT,
                last_probe_latency_ms INTEGER,
                last_seen_online_at TEXT,
                portainer_service_id INTEGER,
                inventory_source TEXT NOT NULL DEFAULT 'manual',
                last_checked_at TEXT,
                last_status TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracker_id INTEGER NOT NULL,
                version TEXT NOT NULL,
                release_name TEXT,
                release_body TEXT,
                previous_version TEXT,
                previous_release_name TEXT,
                release_url TEXT,
                published_at TEXT,
                detected_at TEXT NOT NULL,
                notified_at TEXT,
                FOREIGN KEY (tracker_id) REFERENCES trackers(id) ON DELETE CASCADE,
                UNIQUE (tracker_id, version)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                email TEXT COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
                active INTEGER NOT NULL DEFAULT 1,
                notify_email INTEGER NOT NULL DEFAULT 1,
                notify_pushover INTEGER NOT NULL DEFAULT 0,
                pushover_user_key_enc TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS notification_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel TEXT NOT NULL CHECK (channel IN ('email', 'pushover')),
                status TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'skipped')),
                error TEXT,
                sent_at TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE (event_id, user_id, channel)
            );

            CREATE TABLE IF NOT EXISTS ai_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                tracker_id INTEGER,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (tracker_id) REFERENCES trackers(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS ai_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES ai_conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ai_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracker_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                installed_version TEXT,
                release_version TEXT,
                model TEXT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (tracker_id) REFERENCES trackers(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS portainer_environments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint_id INTEGER NOT NULL UNIQUE,
                name TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'portainer',
                source_endpoint_id TEXT,
                endpoint_url TEXT,
                host TEXT,
                status TEXT,
                endpoint_type TEXT,
                last_seen_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS portainer_sync_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL DEFAULT 'queued',
                requested_by INTEGER,
                requested_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                total_environments INTEGER NOT NULL DEFAULT 0,
                processed_environments INTEGER NOT NULL DEFAULT 0,
                services_found INTEGER NOT NULL DEFAULT 0,
                offline_environments INTEGER NOT NULL DEFAULT 0,
                unexpected_errors INTEGER NOT NULL DEFAULT 0,
                current_environment TEXT,
                message TEXT,
                error TEXT,
                worker_id TEXT,
                FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS portainer_import_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL DEFAULT 'queued',
                requested_by INTEGER,
                requested_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                total_items INTEGER NOT NULL DEFAULT 0,
                processed_items INTEGER NOT NULL DEFAULT 0,
                imported_items INTEGER NOT NULL DEFAULT 0,
                failed_items INTEGER NOT NULL DEFAULT 0,
                current_item TEXT,
                payload_json TEXT NOT NULL,
                message TEXT,
                error TEXT,
                worker_id TEXT,
                FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE SET NULL
            );


            CREATE TABLE IF NOT EXISTS portainer_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint_id INTEGER NOT NULL,
                container_id TEXT NOT NULL,
                container_name TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'portainer',
                stack_name TEXT,
                service_name TEXT,
                labels_json TEXT NOT NULL DEFAULT '{}',
                image TEXT,
                image_id TEXT,
                image_digest TEXT,
                detected_version TEXT,
                detected_repository TEXT,
                repository_override TEXT,
                source_url TEXT,
                published_ports_json TEXT NOT NULL DEFAULT '[]',
                primary_port INTEGER,
                state TEXT,
                container_status TEXT,
                health_status TEXT,
                present INTEGER NOT NULL DEFAULT 1,
                ignored INTEGER NOT NULL DEFAULT 0,
                tracker_id INTEGER,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (tracker_id) REFERENCES trackers(id) ON DELETE SET NULL,
                UNIQUE(endpoint_id, container_id)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                details TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS upgrade_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracker_id INTEGER NOT NULL,
                release_version TEXT NOT NULL,
                release_name TEXT,
                installed_version_at_decision TEXT,
                decision_status TEXT NOT NULL DEFAULT 'review'
                    CHECK (decision_status IN ('review', 'update', 'wait', 'ignore', 'deployed')),
                priority TEXT NOT NULL DEFAULT 'normal'
                    CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
                risk TEXT NOT NULL DEFAULT 'unknown'
                    CHECK (risk IN ('unknown', 'low', 'medium', 'high', 'critical')),
                maintenance_date TEXT,
                checklist_json TEXT NOT NULL DEFAULT '[]',
                rollback_notes TEXT,
                change_record_url TEXT,
                decision_notes TEXT,
                previous_version TEXT,
                deployed_version TEXT,
                deployed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by INTEGER,
                FOREIGN KEY (tracker_id) REFERENCES trackers(id) ON DELETE CASCADE,
                FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL,
                UNIQUE (tracker_id, release_version)
            );

            CREATE INDEX IF NOT EXISTS idx_trackers_enabled ON trackers(enabled);
            CREATE INDEX IF NOT EXISTS idx_events_pending ON events(notified_at, detected_at);
            CREATE INDEX IF NOT EXISTS idx_events_tracker_detected ON events(tracker_id, detected_at DESC);
            CREATE INDEX IF NOT EXISTS idx_reset_expiry ON password_reset_tokens(expires_at, used_at);
            CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation ON ai_messages(conversation_id, id);
            CREATE INDEX IF NOT EXISTS idx_portainer_sync_jobs_status ON portainer_sync_jobs(status, requested_at);
            CREATE INDEX IF NOT EXISTS idx_portainer_import_jobs_status ON portainer_import_jobs(status, requested_at);
            CREATE INDEX IF NOT EXISTS idx_portainer_services_endpoint ON portainer_services(endpoint_id, present);
            CREATE INDEX IF NOT EXISTS idx_portainer_services_tracker ON portainer_services(tracker_id);
            CREATE INDEX IF NOT EXISTS idx_upgrade_decisions_status ON upgrade_decisions(decision_status, priority, maintenance_date);
            CREATE INDEX IF NOT EXISTS idx_upgrade_decisions_tracker ON upgrade_decisions(tracker_id, updated_at DESC);
            """
        )

        # Idempotent migrations from 1.x.
        tracker_columns = [
            "tags TEXT NOT NULL DEFAULT ''",
            "refresh_hours INTEGER NOT NULL DEFAULT 6",
            "current_release_body TEXT",
            "installed_version TEXT",
            "detected_installed_version TEXT",
            "machine_name TEXT",
            "install_host TEXT",
            "install_port INTEGER",
            "install_scheme TEXT NOT NULL DEFAULT 'http'",
            "health_path TEXT NOT NULL DEFAULT '/'",
            "probe_mode TEXT NOT NULL DEFAULT 'manual'",
            "version_probe_path TEXT",
            "version_json_path TEXT",
            "version_regex TEXT",
            "ssh_user TEXT",
            "ssh_port INTEGER NOT NULL DEFAULT 22",
            "docker_container TEXT",
            "ssh_key_name TEXT",
            "last_probe_at TEXT",
            "last_probe_status TEXT",
            "last_probe_error TEXT",
            "last_probe_latency_ms INTEGER",
            "last_seen_online_at TEXT",
            "portainer_service_id INTEGER",
            "inventory_source TEXT NOT NULL DEFAULT 'manual'",
        ]
        for definition in tracker_columns:
            _add_column(conn, "trackers", definition)
        for definition in [
            "previous_version TEXT",
            "previous_release_name TEXT",
            "release_body TEXT",
        ]:
            _add_column(conn, "events", definition)

        for definition in [
            "provider TEXT NOT NULL DEFAULT 'portainer'",
            "source_endpoint_id TEXT",
        ]:
            _add_column(conn, "portainer_environments", definition)
        for definition in [
            "provider TEXT NOT NULL DEFAULT 'portainer'",
            "labels_json TEXT NOT NULL DEFAULT '{}'",
            "container_status TEXT",
        ]:
            _add_column(conn, "portainer_services", definition)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_environment_source "
            "ON portainer_environments(provider, source_endpoint_id) "
            "WHERE source_endpoint_id IS NOT NULL"
        )
        now = utcnow()
        defaults = {
            "default_refresh_hours": str(DEFAULT_REFRESH_HOURS),
            "app_base_url": "",
            "smtp_enabled": "0",
            "smtp_host": "",
            "smtp_port": "587",
            "smtp_security": "starttls",
            "smtp_username": "",
            "smtp_password_enc": "",
            "smtp_from_email": "",
            "smtp_from_name": "Software Release Radar",
            "smtp_timeout": "15",
            "pushover_enabled": "0",
            "pushover_app_token_enc": "",
            "pushover_priority": "0",
            "pushover_sound": "pushover",
            "openai_enabled": "0",
            "openai_base_url": "",
            "openai_api_key_enc": "",
            "openai_model": "",
            "openai_timeout": "120",
            "openai_max_tokens": "1800",
            "openai_auto_analyse": "0",
            "portainer_enabled": "0",
            "portainer_base_url": "",
            "inventory_provider": "portainer",
            "dockhand_base_url": "",
            "dockhand_api_token_enc": "",
            "dockhand_verify_tls": "1",
            "dockhand_timeout": "20",
            "dockhand_sync_hours": "1",
            "dockhand_last_sync_at": "",
            "dockhand_last_sync_status": "never",
            "dockhand_last_sync_error": "",
            "portainer_api_token_enc": "",
            "portainer_verify_tls": "1",
            "portainer_timeout": "20",
            "portainer_sync_hours": "1",
            "portainer_last_sync_at": "",
            "portainer_last_sync_status": "never",
            "portainer_last_sync_error": "",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )
        conn.execute(
            "UPDATE trackers SET refresh_hours = ? WHERE refresh_hours IS NULL OR refresh_hours < 1",
            (DEFAULT_REFRESH_HOURS,),
        )
        conn.execute("UPDATE trackers SET tags = '' WHERE tags IS NULL")
        conn.execute("UPDATE trackers SET health_path = '/' WHERE health_path IS NULL OR health_path = ''")
        conn.execute("UPDATE trackers SET install_scheme = 'http' WHERE install_scheme IS NULL OR install_scheme = ''")
        conn.execute("UPDATE trackers SET probe_mode = 'manual' WHERE probe_mode IS NULL OR probe_mode = ''")
        conn.execute("UPDATE trackers SET ssh_port = 22 WHERE ssh_port IS NULL OR ssh_port < 1")
        conn.execute("UPDATE trackers SET inventory_source = 'manual' WHERE inventory_source IS NULL OR inventory_source = ''")
        _seed_admin(conn)


def get_setting(key: str, default: str | None = None) -> str | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default


def get_settings(keys: list[str]) -> dict[str, str]:
    init_db()
    if not keys:
        return {}
    placeholders = ",".join("?" for _ in keys)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT key, value FROM settings WHERE key IN ({placeholders})", keys
        ).fetchall()
    found = {str(row["key"]): str(row["value"]) for row in rows}
    return {key: found.get(key, "") for key in keys}


def set_setting(key: str, value: str) -> None:
    set_settings({key: value})


def set_settings(values: dict[str, str]) -> None:
    now = utcnow()
    with transaction() as conn:
        for key, value in values.items():
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, str(value), now),
            )


def audit(user_id: int | None, action: str, target_type: str | None = None,
          target_id: str | int | None = None, details: str | None = None) -> None:
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (user_id, action, target_type, target_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, action, target_type, str(target_id) if target_id is not None else None, details, utcnow()),
        )
