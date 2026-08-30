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

## Docker inventory providers

Open **Settings → Docker inventory provider**.

Select either **Portainer** or **Dockhand**. Release Radar saves each provider configuration separately, so switching providers does not discard the other provider's URL or encrypted credential. Existing installations default to Portainer and require no manual migration.

Switching changes which provider is synchronised and displayed, but it does not silently move existing tracker-to-container mappings. Those mappings remain attached to their original provider record until an administrator imports the corresponding service from the newly selected provider. Importing that service explicitly transfers the tracker mapping and clears the previous service link. Switching back exposes the retained inventory again.

For either provider:

- use an HTTPS base URL wherever possible;
- keep TLS certificate verification enabled;
- use a dedicated account or token with only the inventory permissions required;
- test the saved connection before synchronising; and
- review the inventory page before importing trackers.

### Portainer

Create a dedicated Portainer API access token with permission to list the required Docker endpoints, containers and image metadata. Release Radar sends it in the X-API-Key header.

### Dockhand

1. Sign in to Dockhand with an account that can view the required environments and containers.
2. Open your user **Profile** by clicking your avatar in the sidebar, then scroll to **API tokens**.
3. Create a dedicated token for Release Radar and copy the dh_ value when it is shown.
4. In Release Radar, select **Dockhand**, enter the Dockhand origin, such as `https://dockhand.example.com` or `https://dockhand.example.com:8443`, and paste the token. Do not include credentials, a path, query string or fragment in the URL.
5. Save, choose **Test inventory connection**, then open **Inventory** and synchronise.

Release Radar sends the token only as Authorization: Bearer. It stores the token encrypted and never returns it to the browser after saving.

When a reverse proxy terminates HTTPS in front of an HTTP-only Dockhand service, prefer configuring Release Radar with the reverse proxy HTTPS URL. Keep `ALLOW_INSECURE_INTEGRATIONS=false` in that arrangement because the bearer token remains encrypted between Release Radar and the proxy.

If Release Radar instead connects directly to Dockhand over an internal HTTP URL, such as `http://dockhand:3000`, set `ALLOW_INSECURE_INTEGRATIONS=true` in the Release Radar deployment. This is an explicit trusted-network exception because the bearer token crosses that network in cleartext. A reverse proxy used by browser clients does not protect a separate direct HTTP connection from Release Radar to Dockhand.

Dockhand's container route currently returns an empty JSON list both for a genuinely empty environment and when its Docker connection fails. Release Radar therefore calls POST /api/environments/{id}/test before GET /api/containers?env={id}&all=true. Only a successful test permits reconciliation. An unavailable or malformed environment retains its last-known inventory and is shown as offline or error.

Dockhand supplies container IDs, names, image references, state, status, health, labels, ports, networks and Compose labels through its container list. Image IDs are retained when supplied by the installed Dockhand version. Current Dockhand list responses may omit image IDs, in which case Release Radar leaves that optional field empty rather than guessing.

The background inventory worker remains idle when no jobs are queued.
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
| Inventory provider | Use imported Portainer or Dockhand inventory and container state |

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
