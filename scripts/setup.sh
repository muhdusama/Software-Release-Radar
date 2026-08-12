#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "Docker is required. Install Docker Engine or Docker Desktop first."
docker info >/dev/null 2>&1 || fail "Docker is installed but the Docker daemon is not available."
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."

if [[ -e .env ]]; then
  fail ".env already exists. It was not changed. Run 'docker compose up -d --build' to start the existing configuration."
fi

SETUP_NONINTERACTIVE="${RADAR_SETUP_NONINTERACTIVE:-false}"
SETUP_VERSION="${RADAR_SETUP_VERSION:-2.8.0}"
SETUP_BIND_ADDRESS="${RADAR_SETUP_BIND_ADDRESS:-0.0.0.0}"
SETUP_PORT="${RADAR_SETUP_PORT:-9120}"

[[ "$SETUP_VERSION" =~ ^[A-Za-z0-9._-]+$ ]] || fail "RADAR_SETUP_VERSION contains unsupported characters."
[[ "$SETUP_BIND_ADDRESS" =~ ^[A-Za-z0-9:._-]+$ ]] || fail "RADAR_SETUP_BIND_ADDRESS is invalid."
[[ "$SETUP_PORT" =~ ^[0-9]+$ ]] || fail "RADAR_SETUP_PORT must be a number."
(( SETUP_PORT >= 1 && SETUP_PORT <= 65535 )) || fail "RADAR_SETUP_PORT must be between 1 and 65535."

printf 'Software Release Radar first-run setup\n\n'

if [[ "$SETUP_NONINTERACTIVE" == "true" ]]; then
  ADMIN_USERNAME="${RADAR_SETUP_USERNAME:-admin}"
  ADMIN_EMAIL="${RADAR_SETUP_EMAIL:-}"
  ADMIN_PASSWORD="${RADAR_SETUP_PASSWORD:-}"
  [[ -n "$ADMIN_PASSWORD" ]] || fail "RADAR_SETUP_PASSWORD is required in non-interactive mode."
else
  read -r -p "Admin username [admin]: " ADMIN_USERNAME
  ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
  read -r -p "Admin email [optional]: " ADMIN_EMAIL
  read -r -s -p "Admin password: " ADMIN_PASSWORD
  printf '\n'
  read -r -s -p "Confirm admin password: " ADMIN_PASSWORD_CONFIRM
  printf '\n'
  [[ "$ADMIN_PASSWORD" == "$ADMIN_PASSWORD_CONFIRM" ]] || fail "Passwords do not match."
  unset ADMIN_PASSWORD_CONFIRM
fi

[[ "$ADMIN_USERNAME" =~ ^[A-Za-z0-9_.-]{3,64}$ ]] || fail "Username must be 3 to 64 characters using letters, numbers, dots, dashes or underscores."
if [[ -n "$ADMIN_EMAIL" && ! "$ADMIN_EMAIL" =~ ^[^[:space:]#=]+@[^[:space:]#=]+\.[^[:space:]#=]+$ ]]; then
  fail "Email address format is invalid."
fi
[[ ${#ADMIN_PASSWORD} -ge 10 ]] || fail "Password must contain at least 10 characters."

printf 'Generating secure application secrets with a temporary Python container...\n'
GENERATED="$({ printf '%s' "$ADMIN_PASSWORD"; } | docker run --rm -i python:3.13-slim python -c '
import base64, hashlib, os, secrets, sys
password = sys.stdin.read()
salt = secrets.token_bytes(18)
iterations = 600_000
digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
encoded = ":".join([
    "pbkdf2_sha256",
    str(iterations),
    base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
    base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
])
print(encoded)
print(secrets.token_urlsafe(48))
print(base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"))
')"
unset ADMIN_PASSWORD RADAR_SETUP_PASSWORD

# Keep this compatible with the Bash 3.2 version bundled with macOS.
ADMIN_PASSWORD_HASH="$(printf '%s\n' "$GENERATED" | sed -n '1p')"
SECRET_KEY="$(printf '%s\n' "$GENERATED" | sed -n '2p')"
ENCRYPTION_KEY="$(printf '%s\n' "$GENERATED" | sed -n '3p')"
[[ -n "$ADMIN_PASSWORD_HASH" && -n "$SECRET_KEY" && -n "$ENCRYPTION_KEY" ]] || fail "Could not generate the required application secrets."
[[ "$(printf '%s\n' "$GENERATED" | wc -l | tr -d ' ')" == "3" ]] || fail "Unexpected output while generating application secrets."
unset GENERATED

cat > .env <<EOF
RADAR_VERSION=${SETUP_VERSION}
RADAR_BIND_ADDRESS=${SETUP_BIND_ADDRESS}
RADAR_PORT=${SETUP_PORT}
RADAR_SCHEDULER_INTERVAL_SECONDS=60
RADAR_SCHEDULER_LOG_RESULTS=false
RADAR_LOG_LEVEL=INFO

ADMIN_USERNAME=${ADMIN_USERNAME}
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD_HASH=${ADMIN_PASSWORD_HASH}

SECRET_KEY=${SECRET_KEY}
ENCRYPTION_KEY=${ENCRYPTION_KEY}

GITHUB_TOKEN=
SESSION_COOKIE_SECURE=false
TRUST_PROXY_HEADERS=false
EOF
chmod 600 .env
mkdir -p ssh

unset ADMIN_PASSWORD_HASH SECRET_KEY ENCRYPTION_KEY

printf 'Validating Docker Compose configuration...\n'
docker compose config >/dev/null

printf 'Building and starting Software Release Radar...\n'
docker compose up -d --build

printf 'Waiting for the web application to become healthy...\n'
healthy=false
attempt=1
while [[ "$attempt" -le 60 ]]; do
  radar_id="$(docker compose ps -q radar 2>/dev/null || true)"
  status=""
  if [[ -n "$radar_id" ]]; then
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$radar_id" 2>/dev/null || true)"
  fi
  if [[ "$status" == "healthy" ]]; then
    healthy=true
    break
  fi
  if [[ "$status" == "exited" || "$status" == "dead" ]]; then
    docker compose logs --tail=80 radar >&2 || true
    fail "The web container stopped during startup."
  fi
  sleep 2
  attempt=$((attempt + 1))
done

if [[ "$healthy" != "true" ]]; then
  docker compose ps
  docker compose logs --tail=80 radar >&2 || true
  fail "The web application did not become healthy within two minutes."
fi

scheduler_id="$(docker compose ps -q scheduler)"
worker_id="$(docker compose ps -q portainer-worker)"
[[ -n "$scheduler_id" ]] || fail "The automatic release scheduler container was not created."
[[ -n "$worker_id" ]] || fail "The Portainer background worker container was not created."
scheduler_status="$(docker inspect --format '{{.State.Status}}' "$scheduler_id")"
worker_status="$(docker inspect --format '{{.State.Status}}' "$worker_id")"
[[ "$scheduler_status" == "running" ]] || fail "The automatic release scheduler is not running."
[[ "$worker_status" == "running" ]] || fail "The Portainer background worker is not running."

DISPLAY_HOST="$SETUP_BIND_ADDRESS"
if [[ "$DISPLAY_HOST" == "0.0.0.0" || "$DISPLAY_HOST" == "::" ]]; then
  DISPLAY_HOST="localhost"
elif [[ "$DISPLAY_HOST" == *:* ]]; then
  DISPLAY_HOST="[$DISPLAY_HOST]"
fi

printf '\nSoftware Release Radar is ready.\n'
printf 'Open: http://%s:%s\n' "$DISPLAY_HOST" "$SETUP_PORT"
printf 'Admin username: %s\n' "$ADMIN_USERNAME"
printf '\nNext: sign in, add your first tracker, and read docs/DOCKER.md before exposing the service beyond a trusted network.\n'
