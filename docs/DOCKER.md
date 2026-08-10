# Docker deployment

Docker Compose is the primary supported deployment method for Software Release Radar.

## Quick start

```bash
git clone https://github.com/muhdusama/Software-Release-Radar.git
cd Software-Release-Radar
python3 scripts/bootstrap-env.py
docker compose up -d --build
```

Open `http://localhost:9120` after the `software-release-radar` container reports healthy.

## What the stack runs

The Compose stack contains two containers built from the same Python image:

- `software-release-radar` runs the Flask application through Gunicorn.
- `software-release-radar-portainer-worker` processes Portainer synchronisation and bulk import jobs.

Both containers share the `software-release-radar-data` Docker volume, which contains the SQLite database.

## Environment file

`.env` is local deployment configuration and must not be committed. `scripts/bootstrap-env.py` creates it from `.env.example`, generates the Flask session secret and Fernet encryption key, and stores only a PBKDF2 password hash for the initial administrator.

## HTTPS and reverse proxies

`SESSION_COOKIE_SECURE=false` is suitable for a local HTTP test. Set it to `true` when Release Radar is accessed only over HTTPS.

`TRUST_PROXY_HEADERS=false` is the safe default. Set it to `true` only when the application is directly behind one trusted reverse proxy that sets the forwarding headers. Do not enable it when the application is directly exposed to untrusted clients.

## GitHub token

`GITHUB_TOKEN` is optional. Anonymous GitHub API access works for light use, but an access token provides a higher API rate limit.

Use the least-privileged token that meets your needs. Release Radar only needs read access to public release information for public repositories.

## SSH Docker probes

The stack mounts `./ssh` read-only at `/ssh`. SSH Docker probes are optional. If you use them, place only the dedicated key files required for those probes in `./ssh` and add a `known_hosts` file. The application uses strict host-key checking and runs a fixed `docker inspect` command.

## Data

Application state is kept in the named volume `software-release-radar-data`.

Back up the SQLite database before upgrades. The repository includes a portable online backup helper that uses SQLite's backup API:

```bash
./scripts/backup.sh
```

Backups are written to `./backups` by default and are checked with `PRAGMA integrity_check` before the script reports success. Do not copy the live database file directly while writes may be in progress.

## Upgrade

For a source checkout:

```bash
git pull
docker compose build --pull
docker compose up -d
```

Review the changelog before upgrading between public releases.
