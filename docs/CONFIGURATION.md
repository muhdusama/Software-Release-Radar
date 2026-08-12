# Configuration

This guide covers the configuration that a normal Software Release Radar deployment is expected to use.

Start with [Docker deployment](DOCKER.md) if the application is not installed yet.

## Configuration layers

Release Radar has two configuration layers:

1. `.env` contains deployment-level settings and secrets needed before the application starts.
2. The **Settings** page contains application integrations and operational defaults. Sensitive values saved there are encrypted in SQLite with `ENCRYPTION_KEY`.

Do not commit a real `.env` file.

## Deployment environment

The recommended `bash scripts/setup.sh` flow creates `.env` for you.

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `RADAR_VERSION` | yes | `2.8.0` | Image and build version label |
| `RADAR_BIND_ADDRESS` | yes | `0.0.0.0` | Address used to publish the web port on the Docker host |
| `RADAR_PORT` | yes | `9120` | Host port for the web interface |
| `RADAR_SCHEDULER_INTERVAL_SECONDS` | yes | `60` | How often the scheduler looks for trackers that are due |
| `RADAR_SCHEDULER_LOG_RESULTS` | no | `false` | Include detailed check results in scheduler logs |
| `RADAR_LOG_LEVEL` | no | `INFO` | Scheduler log level |
| `ADMIN_USERNAME` | first run | `admin` | Username seeded when the database contains no users |
| `ADMIN_EMAIL` | no | empty | Email for the initial administrator |
| `ADMIN_PASSWORD_HASH` | first run | empty | PBKDF2 hash for the initial administrator |
| `SECRET_KEY` | yes | empty | Flask session signing secret |
| `ENCRYPTION_KEY` | yes | empty | Fernet key used for encrypted application secrets |
| `GITHUB_TOKEN` | no | empty | Raises GitHub API rate limits |
| `SESSION_COOKIE_SECURE` | no | `false` | Restrict session cookies to HTTPS |
| `TRUST_PROXY_HEADERS` | no | `false` | Trust forwarding headers from one directly connected reverse proxy |

Internal Compose values such as `RADAR_DB=/data/radar.db` and `RADAR_SSH_DIR=/ssh` are supplied by the stack and normally do not need to be changed.

`RADAR_BIND_ADDRESS=0.0.0.0` makes the application reachable through Docker host interfaces when the host firewall allows it. Use `127.0.0.1` when a reverse proxy on the same host should be the only path into Release Radar.

### Secret values

`SECRET_KEY` and `ENCRYPTION_KEY` are not optional in a running deployment. The application fails fast if they are missing or invalid.

Do not replace `ENCRYPTION_KEY` after saving encrypted integration credentials unless you intentionally plan to re-enter those credentials. Existing encrypted values cannot be decrypted with a different key.

## General settings

Open **Settings → General** as an administrator.

### Default refresh interval

This becomes the default for new trackers. Individual trackers can use their own interval.

Supported intervals are 1, 2, 3, 6, 12, 24, 48, 72 and 168 hours.

### Application base URL

Set this to the URL users actually use, for example:

```text
https://radar.example.com
```

Password-reset links use this value. It is especially important behind a reverse proxy.

## SMTP email

Open **Settings → SMTP email**.

SMTP is used for release notifications for users who enable email notifications and for password-reset email.

Available fields include SMTP host, port, STARTTLS or implicit TLS/SSL, username, password, timeout, From email and From name.

Use TLS where your mail provider supports it. The saved SMTP password is encrypted and is not displayed again.

After saving, use **Test email** before relying on password reset or release notifications.

## Pushover

Open **Settings → Pushover**.

Configure the application API token, priority and sound. Each user can then save their own Pushover user or group key in their Profile.

The application token and user keys are stored encrypted.

Use **Test Pushover** before relying on push notifications.

## Portainer

Open **Settings → Portainer**.

Portainer integration can discover Docker environments, stacks and containers through one API connection.

Recommended configuration:

- use a dedicated least-privileged API token;
- use HTTPS where possible;
- keep TLS certificate verification enabled;
- use a directly reachable internal endpoint rather than routing management API traffic through an unnecessary public path; and
- test the connection before importing inventory.

Configurable values include Portainer base URL, API token, inventory interval, API timeout and TLS certificate verification.

The Portainer background worker remains idle when no jobs are queued.

## OpenAI-compatible assistant

Open **Settings → AI assistant**.

The assistant is optional. Core release monitoring, due scheduling, version comparison, probes and standard notifications work without an LLM.

The integration uses an OpenAI-compatible Chat Completions endpoint. This can point to OpenAI, LiteLLM or another compatible service.

The base URL must be a complete `http://` or `https://` URL and must not contain embedded credentials.

Configure the base URL, model name, API key, timeout, maximum response tokens and optional automatic analysis of newly detected releases.

Automatic analysis can consume model tokens whenever a new release event is detected. Leave it disabled if deterministic monitoring without model cost is preferred.

Use **Test assistant** after saving the settings.

## Add a tracker

Open **Add software**.

Each tracker requires a software name, GitHub repository in `owner/repository` form, refresh interval and tracking method.

Tracking methods:

- **Latest GitHub release** follows published GitHub Releases.
- **Latest Git tag** follows the most recent tag.

Prereleases are excluded by default.

Optional fields include tags, homepage URL and operational notes.

## Installed deployment context

A tracker can also record where the software runs, including its installed version, machine name, IP address or hostname, HTTP/HTTPS/TCP protocol, service port and health path.

These fields let Release Radar combine upstream release information with local deployment context.

## Installed-version probes

Probe modes are deterministic and do not use an LLM.

| Probe | Use case |
|---|---|
| Manual | You maintain the installed version yourself and optionally test reachability |
| HTTP automatic | Discover a version from a common HTTP response pattern |
| HTTP JSON | Read a version from a configured JSON path |
| HTTP regular expression | Extract a version from the response with a configured expression |
| SSH Docker | Inspect a named remote Docker container through constrained SSH |
| Portainer | Use imported Portainer inventory and container state |

### SSH Docker probe

Place a dedicated private key and `known_hosts` file in the deployment `ssh/` directory.

The application uses strict host-key checking and a fixed Docker inspection command. It does not expose arbitrary remote shell execution through the tracker form.

## User notifications

Administrators manage users from the Users page. Every signed-in user has a dedicated **Notifications** page.

The administrator-wide switch can pause release alerts without disabling SMTP password recovery. Each user then chooses a personal default and Email or Pushover channels. Every software tracker can inherit the personal default, always notify, or remain muted.

A notification is recorded per user and channel so the same release event is not repeatedly delivered after a successful send or deliberate policy skip. Muted events do not become a backlog when alerts are later enabled.

See [Notification controls](NOTIFICATIONS.md) for precedence, examples and operational behaviour.

## Automatic monitoring

The scheduler wakes every 60 seconds by default and asks the release checker for due trackers.

The important distinction is:

```text
Scheduler polling interval ≠ tracker release-check interval
```

A tracker configured for every 24 hours is still checked approximately every 24 hours. The scheduler merely notices when that tracker becomes due.

## Configuration backup

The database contains tracker definitions, users, decisions, integration configuration and encrypted secrets. Back it up with:

```bash
./scripts/backup.sh
```

Your `.env` is separate from the database. Keep an appropriately protected copy of `.env` as part of your normal host backup strategy because its `ENCRYPTION_KEY` is needed to decrypt stored credentials.

Never publish either file.
