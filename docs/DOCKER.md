# Docker deployment

Docker Compose is the primary supported deployment method for Software Release Radar.

The public stack is designed so a self-hoster needs Docker and Docker Compose, not a separately managed Python environment.

## Requirements

- Docker Engine or Docker Desktop
- Docker Compose v2
- Git
- outbound HTTPS access to GitHub
- outbound access to any optional integrations you enable

The default web port is `9120`.

## Recommended first run

```bash
git clone https://github.com/muhdusama/Software-Release-Radar.git
cd Software-Release-Radar
bash scripts/setup.sh
```

The setup script:

1. checks that Docker and Docker Compose are available;
2. asks for the initial administrator username, email and password;
3. generates a PBKDF2 password hash, Flask session secret and Fernet encryption key inside a temporary Python container;
4. writes `.env` with mode `0600`;
5. creates the optional `ssh/` directory;
6. validates the Compose configuration;
7. builds and starts the stack;
8. waits for the web application to report healthy; and
9. confirms the scheduler and Portainer worker are running.

The administrator password itself is not written to `.env`.

When setup finishes, open:

```text
http://localhost:9120
```

## What the stack runs

The Compose stack contains three long-running services built from the same Python application image.

| Compose service | Purpose |
|---|---|
| `radar` | Flask application served by Gunicorn |
| `scheduler` | Runs due release checks automatically and dispatches notifications for new releases |
| `portainer-worker` | Processes Portainer synchronisation and bulk-import jobs |

Compose assigns project-scoped container and volume names automatically. The repository deliberately does not hard-code global container names or a global database-volume name. This prevents two independent checkouts from silently colliding or sharing the same database.

The scheduler wakes every 60 seconds by default, but it only checks trackers whose individual refresh interval is due. The scheduler interval is therefore a lightweight polling interval, not the release-check interval for every tracker.

## Check the deployment

```bash
docker compose ps
```

The `radar` service should show `healthy`. The `scheduler` and `portainer-worker` services should show `running`.

Check the health endpoint:

```bash
curl -fsS http://localhost:9120/healthz
```

Expected shape for v2.8.0:

```json
{"name":"Software Release Radar","status":"ok","version":"2.8.0"}
```

View recent logs:

```bash
docker compose logs --tail=100 radar scheduler portainer-worker
```

## Environment file

`.env` is local deployment configuration and must not be committed.

The safe template is `.env.example`.

| Setting | Purpose | Default |
|---|---|---|
| `RADAR_BIND_ADDRESS` | Address that publishes the web port on the Docker host | `0.0.0.0` |
| `RADAR_PORT` | Host port for the web interface | `9120` |
| `RADAR_SCHEDULER_INTERVAL_SECONDS` | How often the scheduler looks for due trackers | `60` |
| `RADAR_LOG_LEVEL` | Scheduler log level | `INFO` |
| `GITHUB_TOKEN` | Optional GitHub API token for higher rate limits | empty |
| `SESSION_COOKIE_SECURE` | Require secure session cookies | `false` |
| `TRUST_PROXY_HEADERS` | Trust one directly connected reverse proxy | `false` |

`RADAR_BIND_ADDRESS=0.0.0.0` makes the application reachable through the Docker host interfaces when the host firewall permits it. Use `127.0.0.1` when Release Radar should only be reachable through a reverse proxy running on the same host.

`SECRET_KEY`, `ENCRYPTION_KEY` and `ADMIN_PASSWORD_HASH` must contain real secure values. `scripts/setup.sh` generates them for you.

### Manual setup

The Docker-only setup script is recommended. If Python 3 is already installed and you prefer the manual path, this remains available:

```bash
python3 scripts/bootstrap-env.py
docker compose up -d --build
```

Do not copy `.env.example` to `.env` and leave its secret fields empty.

## Automatic release checks

Automatic monitoring is built into the Compose stack.

Each tracker has its own refresh interval. The scheduler calls the deterministic due-check path and only contacts upstream release APIs for trackers that are due.

The scheduler does not require an LLM. Optional AI analysis stays separate from normal release checking.

Useful scheduler logs:

```bash
docker compose logs -f scheduler
```

Allowed scheduler polling values are 30 to 3600 seconds.

## HTTPS and reverse proxies

For a trusted local HTTP deployment, the defaults are:

```text
SESSION_COOKIE_SECURE=false
TRUST_PROXY_HEADERS=false
```

For an HTTPS deployment behind one trusted reverse proxy:

```text
SESSION_COOKIE_SECURE=true
TRUST_PROXY_HEADERS=true
```

Only enable `TRUST_PROXY_HEADERS` when Release Radar is directly behind the proxy that sets the forwarding headers. Do not enable it when untrusted clients can connect directly to the application port.

If the reverse proxy runs on the same Docker host, consider:

```text
RADAR_BIND_ADDRESS=127.0.0.1
```

Recommended reverse-proxy behaviour:

- terminate TLS at the proxy;
- forward traffic to the configured Release Radar host port;
- restrict direct access to that port when practical;
- use a valid certificate; and
- preserve the original HTTPS scheme and host headers.

See [Security hardening](SECURITY-HARDENING.md) for the full production checklist.

## GitHub token

`GITHUB_TOKEN` is optional. Anonymous GitHub API access is sufficient for light use, but the rate limit is lower.

If you configure a token, use the least privilege needed. Tracking public repositories only requires read access to public release information.

## Portainer

Portainer integration is optional.

Use a dedicated, least-privileged API token. TLS verification is enabled by default inside the application. Do not disable certificate verification simply to work around an invalid certificate.

The Portainer worker can remain running when Portainer integration is disabled. It sleeps while no jobs are queued.

## SSH Docker probes

SSH Docker probes are optional.

The stack mounts `./ssh` read-only at `/ssh`. If you use this feature:

- create a dedicated SSH key for Release Radar;
- restrict the remote account as much as practical;
- place only the required key files in `./ssh`;
- create `ssh/known_hosts`; and
- keep strict host-key checking enabled.

Release Radar uses a fixed Docker inspect command rather than arbitrary remote shell commands.

## Data

Application state is stored in the Compose-scoped `radar-data` volume. Docker Compose automatically prefixes the actual Docker volume with the Compose project name, so independent checkouts do not share the same database by accident.

The SQLite database lives at `/data/radar.db` inside the application services.

Do not copy the live SQLite file directly while the application may be writing to it.

## Back up

Create an online SQLite backup:

```bash
./scripts/backup.sh
```

The helper uses SQLite's online backup API inside the application container, validates the result with `PRAGMA integrity_check`, then copies the verified backup to `./backups`.

You can provide a custom timestamp and destination directory:

```bash
./scripts/backup.sh 20260811-010000 /srv/backups/release-radar
```

Keep backups outside the repository and test restores periodically.

## Restore

Restoring replaces the active database, so it requires an explicit confirmation flag.

```bash
bash scripts/restore.sh ./backups/radar-20260811-010000.db --confirm
```

The restore helper:

1. validates the requested backup;
2. creates and validates a new pre-restore safety backup;
3. stops all services that can write the database;
4. uses a one-off maintenance container with elevated filesystem access only for the restore operation;
5. restores the database and returns ownership to the normal non-root `radar` runtime user;
6. validates the restored database;
7. attempts automatic rollback to the safety backup if the requested restore fails;
8. starts the normal non-root services again; and
9. waits for the full stack to return healthy.

The safety backup is retained after a successful restore.

## Upgrade

Back up first:

```bash
./scripts/backup.sh
```

Then update a source checkout:

```bash
git pull --ff-only
docker compose build --pull
docker compose up -d --build
```

Check the health endpoint and logs after the services restart.

Review `CHANGELOG.md` before every upgrade. If a future release requires a special migration step, it will be called out in the release notes and upgrade documentation.

## Stop or remove

Stop the application without deleting data:

```bash
docker compose down
```

Deleting the Compose volume deletes the Release Radar database. Do not use `docker compose down -v` unless you deliberately want to remove all application state or you have a verified backup.

## Troubleshooting

### Web service is unhealthy

```bash
docker compose ps
docker compose logs --tail=150 radar
```

Common causes are missing or invalid `SECRET_KEY` or `ENCRYPTION_KEY` values, an invalid `.env`, or a data-volume problem.

### Scheduler is restarting

```bash
docker compose logs --tail=150 scheduler
```

Check `RADAR_SCHEDULER_INTERVAL_SECONDS` and confirm it is an integer between 30 and 3600.

### GitHub checks are rate limited

Add a least-privileged `GITHUB_TOKEN` to `.env`, then restart:

```bash
docker compose up -d
```

### Portainer connection fails

Use the Settings page to test Portainer. Verify the URL, API token, certificate trust and network path from the Release Radar service to Portainer.

### Need more help

Use GitHub Discussions for deployment and configuration questions. Use GitHub Issues for reproducible defects. Follow `SECURITY.md` for vulnerabilities.

See [Configuration](CONFIGURATION.md), [Architecture](ARCHITECTURE.md) and [Security hardening](SECURITY-HARDENING.md) for more detail.
