#!/bin/sh
set -eu

STAMP="${1:-$(date +%Y%m%d-%H%M%S)}"
DEST_DIR="${2:-./backups}"
CONTAINER_COPY="/tmp/radar-backup-${STAMP}.db"
HOST_COPY="${DEST_DIR}/radar-${STAMP}.db"

mkdir -p "$DEST_DIR"

cleanup() {
  docker compose exec -T radar python -c "from pathlib import Path; Path('${CONTAINER_COPY}').unlink(missing_ok=True)" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker compose exec -T radar python -c "import sqlite3; source=sqlite3.connect('/data/radar.db'); target=sqlite3.connect('${CONTAINER_COPY}'); source.backup(target); target.close(); source.close()"
docker compose exec -T radar python -c "import sqlite3; conn=sqlite3.connect('file:${CONTAINER_COPY}?mode=ro', uri=True); result=conn.execute('PRAGMA integrity_check').fetchone()[0]; conn.close(); assert result == 'ok', f'Backup integrity check failed: {result}'"
docker compose cp "radar:${CONTAINER_COPY}" "$HOST_COPY" >/dev/null

printf 'Backup created: %s\n' "$HOST_COPY"
printf 'SQLite integrity_check: ok\n'
