#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  printf 'Usage: %s BACKUP.db --confirm\n' "$0" >&2
  exit 2
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ $# -eq 2 && "$2" == "--confirm" ]] || usage
BACKUP="$1"
[[ -f "$BACKUP" ]] || fail "Backup file not found: $BACKUP"

command -v docker >/dev/null 2>&1 || fail "Docker is required."
docker info >/dev/null 2>&1 || fail "Docker is installed but the Docker daemon is not available."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."

ABS_BACKUP="$(cd "$(dirname "$BACKUP")" && pwd)/$(basename "$BACKUP")"
STAMP="$(date +%Y%m%d-%H%M%S)"
SAFETY_STAMP="pre-restore-${STAMP}"
SAFETY_BACKUP="${ROOT}/backups/radar-${SAFETY_STAMP}.db"

validate_backup() {
  local source="$1"
  docker run --rm -v "$source:/restore.db:ro" python:3.13-slim python -c "import sqlite3; conn=sqlite3.connect('file:/restore.db?mode=ro', uri=True); result=conn.execute('PRAGMA integrity_check').fetchone()[0]; conn.close(); assert result == 'ok', f'Backup integrity check failed: {result}'"
}

restore_database() {
  local source="$1"
  docker compose run --rm --no-deps -v "$source:/restore.db:ro" radar python -c "import os,shutil,sqlite3; src=sqlite3.connect('file:/restore.db?mode=ro', uri=True); result=src.execute('PRAGMA integrity_check').fetchone()[0]; src.close(); assert result == 'ok', f'Backup integrity check failed: {result}'; target='/data/radar.db'; [os.remove(path) for path in (target + '-wal', target + '-shm') if os.path.exists(path)]; shutil.copyfile('/restore.db', target); conn=sqlite3.connect(target); result=conn.execute('PRAGMA integrity_check').fetchone()[0]; conn.close(); assert result == 'ok', f'Restored database integrity check failed: {result}'"
}

printf 'Validating requested backup before restore...\n'
validate_backup "$ABS_BACKUP"

printf 'Creating a safety backup of the current database...\n'
bash scripts/backup.sh "$SAFETY_STAMP" "${ROOT}/backups"
[[ -f "$SAFETY_BACKUP" ]] || fail "The pre-restore safety backup was not created. Restore has been cancelled."
validate_backup "$SAFETY_BACKUP"
printf 'Safety backup: %s\n' "$SAFETY_BACKUP"

printf 'Stopping Release Radar services...\n'
docker compose stop scheduler portainer-worker radar >/dev/null

restore_failed=false
rollback_failed=false
if ! restore_database "$ABS_BACKUP"; then
  restore_failed=true
  printf 'Requested restore failed. Rolling back to the pre-restore safety backup...\n' >&2
  if ! restore_database "$SAFETY_BACKUP"; then
    rollback_failed=true
  fi
fi

printf 'Starting Release Radar services...\n'
docker compose up -d >/dev/null

if [[ "$rollback_failed" == "true" ]]; then
  printf 'CRITICAL: the requested restore and automatic rollback both failed.\n' >&2
  printf 'Safety backup retained at: %s\n' "$SAFETY_BACKUP" >&2
  printf 'Inspect the data volume before using the application.\n' >&2
  exit 1
fi

if [[ "$restore_failed" == "true" ]]; then
  printf 'ERROR: requested restore failed. The original database was restored from the safety backup and services were restarted.\n' >&2
  printf 'Safety backup retained at: %s\n' "$SAFETY_BACKUP" >&2
  exit 1
fi

printf 'Restore completed successfully from: %s\n' "$ABS_BACKUP"
printf 'Pre-restore safety backup retained at: %s\n' "$SAFETY_BACKUP"
printf 'Run: docker compose ps\n'
