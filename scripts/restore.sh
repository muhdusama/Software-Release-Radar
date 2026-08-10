#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  printf 'Usage: %s BACKUP.db --confirm\n' "$0" >&2
  exit 2
}

[[ $# -eq 2 && "$2" == "--confirm" ]] || usage
BACKUP="$1"
[[ -f "$BACKUP" ]] || { printf 'ERROR: backup file not found: %s\n' "$BACKUP" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || { printf 'ERROR: Docker is required.\n' >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { printf 'ERROR: Docker Compose v2 is required.\n' >&2; exit 1; }

ABS_BACKUP="$(cd "$(dirname "$BACKUP")" && pwd)/$(basename "$BACKUP")"

printf 'Validating backup before restore...\n'
docker run --rm -v "$ABS_BACKUP:/restore.db:ro" python:3.13-slim python -c "import sqlite3; conn=sqlite3.connect('file:/restore.db?mode=ro', uri=True); result=conn.execute('PRAGMA integrity_check').fetchone()[0]; conn.close(); assert result == 'ok', f'Backup integrity check failed: {result}'"

printf 'Stopping Release Radar services...\n'
docker compose stop scheduler portainer-worker radar >/dev/null

restore_failed=false
if ! docker compose run --rm --no-deps -v "$ABS_BACKUP:/restore.db:ro" radar python -c "import shutil,sqlite3; src=sqlite3.connect('file:/restore.db?mode=ro', uri=True); result=src.execute('PRAGMA integrity_check').fetchone()[0]; src.close(); assert result == 'ok', f'Backup integrity check failed: {result}'; shutil.copyfile('/restore.db','/data/radar.db'); conn=sqlite3.connect('/data/radar.db'); result=conn.execute('PRAGMA integrity_check').fetchone()[0]; conn.close(); assert result == 'ok', f'Restored database integrity check failed: {result}'"; then
  restore_failed=true
fi

printf 'Starting Release Radar services...\n'
docker compose up -d >/dev/null

if [[ "$restore_failed" == "true" ]]; then
  printf 'ERROR: restore failed. Services were started again, but the database state must be checked.\n' >&2
  exit 1
fi

printf 'Restore completed successfully from: %s\n' "$ABS_BACKUP"
printf 'Run: docker compose ps\n'
