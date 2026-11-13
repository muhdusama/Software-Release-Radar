# Changelog

All notable changes to Software Release Radar are documented here.

The project follows semantic versioning for public releases and the Keep a Changelog format.

Format reference: https://keepachangelog.com/en/1.1.0/

## [Unreleased]

### Added

- Changes since your version: the upgrade plan lists every stored release
  between the installed version and the target, newest first, with the
  release notes. Each release is flagged for breaking changes, migration
  steps, security fixes and deprecations using headings, keywords and
  Conventional Commit `!` markers, never an LLM, and quotes the matching
  lines. CVE and GHSA identifiers in the notes link to OSV. A note says when
  the installed version is older than the stored history. Release notes are
  shown as escaped plain text.

### Changed

- New trackers now record up to 30 recent releases on their first check
  (was 10), so the changes list covers a longer upgrade gap.
- The container image now runs Python 3.15 (`python:3.15-slim`). CI runs the
  tests and the dependency and Bandit audits on both Python 3.13 and 3.15.

## [2.14.0] - 2026-11-13

### Added

- GitLab, Codeberg, Gitea and Forgejo release sources. Paste a gitlab.com,
  codeberg.org or gitea.com project URL, or use `gitlab:host/group/project`
  or `gitea:host/owner/repository` for a self-hosted forge. Public projects
  only. The latest release is the highest version rather than the most
  recently published backport, and the GitHub rate-limit cooldown no longer
  pauses trackers on other forges. See `docs/INTEGRATIONS.md`.
- Read-only REST API under `/api/v1` (status, trackers, releases, history and
  upgrade decisions) using the existing Profile API keys or the browser
  session. It reuses the MCP read projections, permissions and size limits.
  Twenty failed key attempts from one address block it for 15 minutes.
- Prometheus metrics at `/metrics`: check success, update availability, probe
  status and latency, last check time, attention and pending notification
  counts, decision counts and the GitHub cooldown.
- Private maintenance calendar (ICS). Profile can create, replace or revoke a
  subscription link that lists planned upgrade dates as all-day events.
- Optional proxy sign-in for Authelia, Authentik or oauth2-proxy with
  `RADAR_FORWARD_AUTH_HEADER` and `RADAR_FORWARD_AUTH_TRUSTED_PROXIES`. The
  header is trusted only from the listed proxy addresses and must name an
  existing active user.
- The command palette finds tracked software as well as pages and actions,
  and opens the upgrade plan for the selected software.
- New trackers now start with recent history. The first check records up to
  10 recent upstream releases (release strategy only) with their publish
  dates, so History, the activity chart and upgrade evidence are useful
  straight away. Seeded releases are marked as already notified and never
  trigger alerts or automatic analysis. Trackers that already have history
  are left unchanged and make no extra GitHub request.
- Zero-typing inventory import: the Inventory page shows a Suggested trackers
  review for untracked containers. Suggestions come from image labels or from
  a curated, versioned list of well-known self-hosted images
  (`radar/known_images.py`), and each row shows its source. Track selected
  creates the trackers in one request and reports created, skipped and
  invalid counts. No GitHub call is made during the request; the scheduled
  check validates the repositories.
- First-run administrator setup in the browser. `ADMIN_PASSWORD_HASH` is now
  optional in `docker-compose.yml`. When no users exist, every page redirects
  to `/setup`, which requires a one-time setup token printed to the web
  container log (`docker compose logs radar | grep setup`).
- Webhook, ntfy and Gotify release-alert channels, configured by an
  administrator under Settings, Other channels. Each is enabled separately,
  delivers once per release rather than once per user, and has a Send test
  notification button. The webhook sends a JSON payload (see
  `docs/NOTIFICATIONS.md`) with an optional bearer token and an optional
  `X-Radar-Signature` HMAC-SHA256 header. Release notes are never sent.
- The Notifications page lists which channels are ready to deliver, and shows
  administrators a Recent delivery failures section.

### Changed

- The command palette follows the ARIA combobox pattern: the search box owns
  the result list, the active result is announced with
  `aria-activedescendant`, result counts are announced politely, Tab stays
  inside the dialog and focus returns to where it was on close. Filtered
  results are now actually hidden; previously the list was filtered for the
  keyboard but every item stayed visible.
- The Assistant's release comparison pages back through up to 300 releases
  until it finds the installed version, instead of stopping at 20.
- The pre-upgrade checklist is now a single editable list. Each item has a
  stable ID, so a tick stays with its item when other items are edited,
  removed or added. Previously ticks were stored by position and could move
  to the wrong item, and the list was shown twice (as checkboxes and again in
  a text box). Existing checklists load unchanged and gain IDs on the next
  save. MCP and CLI callers may pass an optional `id` per item.
- Dashboard software rows show Plan, Check and a More menu instead of up to
  eight buttons. Delete moved into the menu and its confirmation says it
  cannot be undone.
- The software list header and rows share one column layout, so headers line
  up with their columns and no longer overflow. Per-cell labels are hidden on
  desktop and remain on narrow screens.
- Timestamps show in the viewer's local time, with UTC in the tooltip.
- Versions show first, with the release name underneath only when it adds
  information.
- A tracker without an installed version is no longer listed under Needs
  attention. Trackers whose versions cannot be compared still are.
- Keyboard shortcuts follow the sidebar links, so standard users are not sent
  to administrator pages, `A` opens Add software, `Ctrl K` is shown outside
  macOS, and shortcuts work under a sub-path.
- The update activity chart explains why it is empty on a new installation.
- Fleet: correct pluralisation, a neutral Not probed state instead of a green
  "0 online", and no placeholder host text.
- Inventory: Synchronise now is disabled while the integration is off.
- Upgrade decision: the change record field is labelled "Change record link".

### Fixed

- A fresh installation could fail to start: the two web workers, scheduler
  and worker opened the new database together, and one could exit with
  "database is locked" while switching to WAL or "duplicate column name"
  during migrations. The WAL switch now retries briefly and migrations run
  under a write lock.
- An `ADMIN_PASSWORD_HASH` that is not a valid `pbkdf2_sha256` hash no longer
  creates an administrator who can never sign in. The error is logged and the
  application falls back to `/setup`.
- Release alerts were never marked as delivered, so Pending alerts on the
  dashboard grew without end and failed or interrupted deliveries were never
  retried. The scheduler now dispatches every pending alert each cycle, oldest
  first (50 per cycle), and sets `notified_at` once every delivery is sent,
  skipped, or failed with its attempts used up.
- Failed deliveries are retried up to 5 times, waiting 5 minutes multiplied by
  the attempts so far between tries.
- A timeout or other network error while reading a Pushover or AI response no
  longer aborts the whole notification cycle. Each delivery is isolated.
- An AI auto-analysis failure can no longer stop the release alert.
- `radar.checker --notify` no longer marks events as notified when delivery
  failed.
- A failed Portainer or Dockhand inventory sync during checks and probes is now
  logged as a warning (the check still continues).

### Compatibility

- Additive schema only: two columns on `notification_deliveries` (`attempts`,
  `last_attempt_at`) and a new `system_notification_deliveries` table. Older
  versions ignore them and keep working against an upgraded database.
- Upgrade safety: on the first scheduler cycle after upgrading, pending alerts
  detected more than 7 days earlier are closed without sending. The same rule
  applies after a long outage. Newer pending alerts that were already sent are
  closed without a duplicate; others are sent.
- Webhook, ntfy and Gotify are off by default. They follow the system-wide
  safety switch and the first active administrator's notification preferences,
  including per-software Mute and the personal default.
- Previously, a user whose Pushover or SMTP provider was disabled in Settings
  had a retryable failed row. That case is now recorded as skipped.
- Rollback to an earlier version leaves pending alerts without `notified_at`
  again, and the new channels stop sending.

## [2.13.0] - 2026-11-13

### Added

- MCP keys that never expire. An administrator enables them in Settings, MCP
  server; users then choose Never expires when creating a key in Profile. Such
  keys still stop working when revoked, after a password change or when the
  account is deactivated.

### Compatibility

- Off by default. No dependency or schema change; a key without expiry stores
  `never` in the existing expiry column.
- Turning the setting off stops new keys without expiry but keeps existing ones;
  revoke them from Settings if required.
- Rollback to v2.12.0 or earlier rejects keys that never expire.

## [2.12.0] - 2026-11-13

### Added

- MCP server area in Settings for administrators: an access switch, the scopes
  keys may use, whether standard users may use keys, MCP rate limits and a list
  of every user's keys with revoke. Changes apply to the next MCP request
  without a restart.

### Compatibility

- No new dependency or schema change. Policy is stored in the existing settings
  table; unset values keep v2.11.0 behaviour, so upgrades change nothing until
  an administrator saves the MCP section.
- Clearing a scope removes it from existing keys until it is allowed again.
  Network, HTTPS and proxy rules and the authentication failure limit remain
  environment settings.
- Rollback to v2.11.0 ignores the stored MCP policy and rate limits.

## [2.11.0] - 2026-11-02

### Added

- Optional built-in MCP HTTP service with browser-managed scoped API keys,
  bounded cached reads, tracker and upgrade-review writes, constrained checks,
  probes and queued inventory sync, audited durable operation ownership and
  explicitly confirmed offline recovery.
- Isolated SDK/container, backup/restore, restart and additive rollback acceptance.

### Fixed

- Inventory sync enqueue is atomic across workers.
- Browser and MCP upgrade decisions use release-bound integer revisions, preventing
  stale reviews from overwriting a concurrent save or deployed decision.
- The `decide` and `mark-deployed` commands now join the same revision contract.
  Each reads, validates, saves and audits in one immediate transaction, so a CLI
  change invalidates an earlier browser or MCP read, cannot overwrite a deployed
  decision, and is never saved without its audit entry.

### Compatibility

- Adds the `mcp` Python dependency to the image. The MCP service is a separate,
  opt-in Compose profile; existing deployments run unchanged until it is enabled.
- Applies additive startup migrations: MCP key, lease and rate tables, an audit
  `api_key_id` column and an upgrade-decision `revision` column. Version 2.10.9
  ignores these additions, so its image remains a valid rollback.
- Deployments that override the data mount must give the `mcp` service the same
  `/data` and `/ssh` mounts as the other services. Stop every writer, including
  `mcp`, before restoring a database backup.

## [2.10.9] - 2026-10-24

### Fixed

- Dashboard installed-version labels now identify the tracker's recorded inventory provider. Dockhand mappings display Dockhand instead of the legacy internal probe name Portainer.
- Probe setup guidance now refers to inventory mappings for either provider.

### Compatibility

- Display-only correction. No mapping, configuration, dependency or database schema change.

## [2.10.8] - 2026-10-24

### Added

- An explicit inventory-rebinding command with a dry run, expected previous mapping, provider and ownership checks, and atomic validation for batches. Rebinding preserves tracker preferences, manual installed versions, release sources, history and upgrade decisions.

### Fixed

- Dockhand probes now check environment availability before trusting a cached running-container record.
- Where only a legacy version label is available, Dockhand can inspect the individual container for a validated `APP_VERSION`. Explicit Release Radar and OCI version labels retain priority. Only the allowlisted version is used; arbitrary environment values are not stored.
- Rebinding clears old probe results until the new mapping is tested and uses the target container's detected version instead of retaining a different container's observation.

### Compatibility

- No new dependency or database schema migration. Provider changes do not automatically guess or transfer mappings.
- Optional Dockhand version inspection uses the existing token and container-inspection permission. If inspection is unavailable, normal label detection remains available; no additional grant is requested automatically.
- Back up the database and private environment before applying reviewed mapping changes. Retain the previous image and the expected mapping IDs for rollback.

## [2.10.7] - 2026-10-24

### Added

- SearXNG rolling-release checks and bounded history from its official `master` commit history, using the existing GitHub authentication and rate-limit recovery path.
- Date-and-commit version matching for application and Docker formats, with conservative handling of different revisions on the same date.

### Changed

- Rolling date updates carry unknown risk instead of semantic version risk estimates.
- Source commit links and messages retain their provenance in upgrade analysis; they do not claim that a candidate image has been published or tested.
- Tracking controls and version labels describe upstream versions without assuming every source publishes Git tags.

### Compatibility

- Existing SearXNG release trackers adopt rolling history automatically. No new dependency, configuration or database migration beyond v2.10.6 is required.
- Existing trackers, installed versions, decisions, history and private configuration are preserved.

## [2.10.6] - 2026-10-24

### Fixed

- GitHub rate limits now defer and retry affected checks after the provider cooldown instead of waiting the full tracker refresh interval.
- Shared retry state survives restarts and avoids repeated outbound requests while GitHub is rate limited. Ordinary permission failures remain distinct.
- Single and bulk checks identify deferred work instead of reporting it as successfully checked.
- Default inventory sources now identify the application upstreams for Portfolio Performance and Organizr instead of their container packaging repositories.
- Portfolio Performance application metadata takes precedence over an inherited legacy base-image version label.
- Organizr v2 tracking uses its official version-history feed rather than the old v1 release page.

### Documentation

- Added minimal GitHub token permissions, environment setup and rate-limit recovery guidance.

### Compatibility

- Applies an additive internal retry-state migration on startup. Existing configuration, trackers, decisions and history are preserved.
- Back up the database and private environment before upgrading; retain the previous image for rollback.

## [2.10.5] - 2026-10-23

### Changed

- Kept the product roadmap on GitHub only, alongside the comparison guide and application revision updates.
- Removed Roadmap from app navigation, the command palette, routes, templates, supporting styles and container packaging.
- Retained Contributors, Codex credit and the AI development and maintenance disclosure in the app.

### Compatibility

- The former `/roadmap` app URL now returns 404. The roadmap remains linked from the repository README.
- No database migration, new dependency or configuration requirement.

## [2.10.4] - 2026-10-23

### Changed

- Kept the product comparison and application revision updates on GitHub only.
- Removed Compare and Revisions from app navigation, the command palette, routes, templates and container packaging.
- Retained the in-app Roadmap, Contributors and AI development disclosure.

### Compatibility

- The former `/about` and `/revisions` app URLs now return 404. The comparison guide and changelog remain linked from the repository README.
- No database migration, new dependency or configuration requirement.

## [2.10.3] - 2026-10-22

### Added

- A revision selector that defaults to the latest published release, with specific-version links and an all-revisions view.
- An authenticated Contributors page with visible OpenAI Codex credit and links, accessible from navigation and the command palette.
- A dedicated disclosure of AI assistance in software development and maintenance, separate from the optional in-app Assistant.

### Changed

- Redesigned Compare with a focused introduction, decision cards, current-versus-planned scope, complementary-tool cards and a practical example.
- Kept comparisons respectful and encouraged readers to explore Diun, WUD, Renovate and Trivy.
- Bundled canonical contributor documentation with the application.

### Compatibility

- No database migration, new dependency or configuration requirement.

## [2.10.2] - 2026-10-22

### Changed

- Reorganised the roadmap as a Now, Next, Then, Later and Exploring timeline, with concise outcomes and clear delivery status.
- Added a responsive timeline page with numbered milestones, stage shortcuts and keyboard-accessible expandable scope and acceptance criteria.
- Kept repository and in-app roadmap content in one canonical document. Future stages show priority order without promising delivery dates.

### Compatibility

- Presentation and documentation update only. No database migration, new dependency or configuration requirement.

## [2.10.1] - 2026-10-22

### Documentation

- Linked OpenAI Codex's GitHub profile in the contributor credits and README.
- Updated the comparison guide and README to express appreciation for Diun, WUD, Renovate and Trivy, encourage readers to explore them, and describe how their capabilities complement Software Release Radar.
- Kept Release Radar's distinct focus on upgrade decisions, feature gains, removals and the cost of waiting, with current image-analysis limits explicit.

### Compatibility

- Documentation and release metadata only. No application behaviour, database schema, dependency or configuration changes.

## [2.10.0] - 2026-10-22

### Added

- Authenticated About, Revision updates and Roadmap pages, accessible from navigation and the command palette. Revision and roadmap content is bundled with the application from the canonical repository documents.
- A practical comparison with Diun, WUD, Renovate and Trivy that explains the value and limits of reviewing an update before deployment.
- Recorded image metadata in the Assistant context when a valid inventory mapping is available, with observation times and explicit completeness and freshness caveats.

### Changed

- Release analysis now asks for features gained, features removed or deprecated, what you miss by waiting, compatibility requirements and evidence gaps before a recommendation.
- Browser and service paths share release-context builders and analysis prompts.
- Refreshed the README and roadmap, separating shipped capabilities from planned image preflight and supply-chain checks.

### Fixed

- Kept mobile navigation controls on one row and corrected outdated dashboard scheduler wording.
- Form-based Assistant chat sends each question once and only saves a conversation turn after a successful model response.
- Assistant context treats tracker, inventory and upstream fields as untrusted data.
- Release comparisons stay anchored to the tracked target instead of including newer releases returned by a later history lookup.
- Assembled analysis context stays within the AI request limit, with missing boundaries and shortened evidence explicitly identified.

### Compatibility

- No database schema migration, new dependency or new configuration requirement. Existing tracker, inventory, notification and deployment settings are retained.
- Image analysis uses recorded inventory metadata and GitHub release notes. Candidate-image inspection, CVE/SBOM scans, signature verification and automated deployment are not included.

## [2.9.3] - 2026-10-19

### Changed

- The sidebar and sign-in page now show that Software Release Radar is developed and maintained by IMUVERSE, with a link to imuverse.com.

### Documentation

- Added IMUVERSE attribution to the README and refreshed the preview screen captures for v2.9.3, still using fictional demo data only.

## [2.9.2] - 2026-10-18

### Fixed

- Disabled Gunicorn's unused control socket. This removes a harmless permission error at start-up without making the application directory writable or changing the non-root container user.
- Fixed an overlap between the Fleet machine/service summary and the inventory setup notice when no provider is configured.
- Set owner-only permissions on verified SQLite backup files created by the backup helper, including copied backups on the host.

### Documentation

- Replaced outdated hand-drawn preview mock-ups with four actual v2.9.1 screen captures: Dashboard, Upgrade decisions, an Upgrade plan and Fleet. Captures use fictional demo data only, including documentation-reserved network addresses, with no deployment-specific information.
- Updated the README's product overview, setup instructions, formatting, links and release-readiness wording to reflect the current application.
- Corrected contributor acknowledgements and added Claude Code alongside OpenAI Codex.
- Refreshed the repository description and topics to reflect Dockhand support and upgrade management.

### Compatibility

- No database schema migration, new configuration requirement or change to the existing data volume. This is a maintenance update on top of v2.9.1.

## [2.9.1] - 2026-10-18

### Fixed

- `python -m radar.checker` initialises the database schema again before checking. Since 2.9.0 it failed with `no such table: trackers` on a database that the web service had not already initialised.

## [2.9.0] - 2026-10-18

### Added

- Dockhand support as an alternative Docker inventory provider alongside Portainer, including encrypted API-token storage, provider-specific synchronisation, environment availability checks and inventory normalisation.
- A clearly labelled Global defaults section for inherited software notification behaviour and delivery channels.

### Changed

- Docker inventory integration now uses a provider abstraction while preserving the existing Portainer-compatible database and Compose service names for backwards-compatible upgrades.
- Provider switching keeps existing tracker mappings attached to their original provider until an administrator explicitly imports and rebinds the corresponding service from the active provider.
- Gunicorn's minimum supported version is now 26.2.0.
- `cryptography`'s minimum supported version is now 50.0.1.
- `regex`'s minimum supported version is now 2026.9.3.
- Database schema setup and migrations now run once when each process starts, instead of on every settings read and release check. This removes a write transaction from every page request and scheduler cycle.
- Integration transport rules (HTTPS for credential-bearing requests, same-origin credential redirects, bounded responses, SMTP TLS, Assistant size limits and safe probe regular expressions) now live in the code that uses them instead of being patched into the standard library at import time. SMTP now refuses cleartext remote delivery before login rather than after it.
- The Content Security Policy no longer allows inline script. Page scripts now load from `radar/static/pages/`, inline event handlers were replaced with listeners, and the two overlapping security-header handlers were merged into one.
- `radar.web.create_app()` is now the single application factory and installs every route and protection; `radar.application.create_app()` remains as the Gunicorn entry point. No module replaces registered view functions any more, and templates read the version from `radar/version.py`.
- Docker Compose now names its image `ghcr.io/muhdusama/software-release-radar:${RADAR_VERSION}`, so a published release can be run with `docker compose pull` and `docker compose up -d --no-build`. `scripts/setup.sh` still builds locally.
- The sidebar shows a link to the source repository next to the version.
- `docker/setup-qemu-action` is updated from v4.2.0 to v4.3.0 using its immutable commit SHA.

### Fixed

- Dashboard bulk "Check upstream now" and "Probe installed services" no longer fail with a server error when the selection includes an inventory-linked tracker (`sync_inventory` was never imported).
- Cancelling a delete or deployment confirmation no longer leaves the form in a stuck "working" state.
- Inventory probes now fail closed when a tracker mapping belongs to a different provider than the currently active inventory provider, preventing stale cross-provider version or state reporting.
- Offline or malformed Dockhand environment responses preserve last-known-good inventory instead of incorrectly marking existing containers absent.
- Dockhand due-sync scheduling now uses Dockhand-specific timing settings, and Dockhand origin validation rejects embedded credentials, paths, queries and fragments.
- Per-software notification preference changes now save immediately without reloading the Notifications page.
- Bulk software preferences and global notification defaults now save without clearing the current software filter.
- The Notifications software search is retained for the browser session, including after a manual refresh.

### Security

- `radar.web.create_app()` previously served a password-reset handler that built reset links from the request Host header. Only `radar.application.create_app()`, which the container uses, replaced it. The insecure handler has been removed.
- Gunicorn 26.2.0 includes upstream HTTP/2 request-policy hardening.
- Dependency minimums were refreshed after upstream security and reliability maintenance in `cryptography` and `regex`.

### Validated

- PR #15 passed the complete Python 3.13 regression suite, dependency and Bandit security audit, and public Docker setup, backup, restore and persistent-state acceptance workflow before merge.
- PRs #22 through #25 each passed the required Python 3.13 tests, dependency and Bandit security audit, and public Docker setup and recovery acceptance workflow on their final merge heads.

---

## [2.8.0] - 2026-08-12

### Added

- Persistent per-user, per-address, daily and concurrency controls for authenticated Assistant requests.
- Bounded Assistant prompt, response-token, provider-timeout and provider-response limits.
- Recent-analysis reuse and bounded retained Assistant history.
- Timeout-capable, size-bounded execution for user-defined HTTP version regular expressions.
- Dedicated public documentation for password-reset, Assistant, integration-transport and workflow security controls.
- Inline Fleet editors for machine, software and stack or folder display names.
- A dedicated Notifications page with administrator-wide, personal, channel and per-software controls.
- Portainer source-name reconciliation with explicit local display-name overrides.

### Changed

- Password-reset email now uses only the configured and validated application origin, never the request `Host` value.
- Password-reset email delivery is queued outside the browser request and response timing is normalised to reduce identity-dependent differences.
- Credential-bearing remote HTTP integrations require HTTPS by default.
- Remote SMTP delivery requires STARTTLS or implicit TLS by default.
- Explicit trusted-network cleartext exceptions require `ALLOW_INSECURE_INTEGRATIONS=true`.
- All third-party GitHub Actions are pinned to immutable full commit SHAs.
- Portainer synchronisation now refreshes linked tracker names after environment, Compose service, container or stack renames while preserving local aliases.
- Muted notification deliveries are recorded as skipped so re-enabling alerts does not create an old-release backlog.

### Security

- Remediated all six validated findings from the 2026-08-12 Codex Security audit.
- Added regression coverage for trusted reset origins, Assistant abuse controls, credential transport, response limits, regular-expression timeouts and immutable workflow references.

### Validated

- Python compilation and the complete automated regression suite pass.
- `pip-audit` and the reviewed Bandit security gate pass.
- The real Docker setup, health, backup, restore and persistent-state acceptance workflow passes.

---

## [2.7.0] - 2026-08-11

### Added

- GNU AGPL-3.0 open-source publication baseline.
- Sanitised Python 3.13 application source imported without the private Gitea history.
- Production Dockerfile running the application as a non-root user.
- Three-service Docker Compose stack for the web application, automatic release scheduler and Portainer background worker.
- Built-in due-check scheduler so automatic release monitoring does not depend on an external cron job.
- Docker-only first-run setup that generates secure application secrets, seeds the first administrator and waits for the stack to become healthy.
- Docker-only SQLite online backup helper with `PRAGMA integrity_check` validation.
- Guarded restore helper with a verified pre-restore safety backup and automatic rollback attempt when restoration fails.
- SQLite-backed login throttling shared across Gunicorn workers.
- Password-reset request throttling with a generic public response to avoid account enumeration.
- Comparable password-hash work for unknown usernames to reduce an obvious login timing difference.
- Continuous integration for Python compilation, the complete test suite and the full public Docker lifecycle.
- Blocking dependency vulnerability auditing with `pip-audit`.
- Reviewed Bandit security scanning that rejects new medium or high severity, high-confidence findings.
- Dependabot configuration for Python, GitHub Actions and Docker dependencies.
- Version-safe GHCR multi-architecture image publishing workflow for `linux/amd64` and `linux/arm64`.
- Structured GitHub bug report and feature request forms.
- Pull request validation and security checklist.
- Community code of conduct.
- GitHub Discussions and roadmap polling process.
- Buy Me a Coffee, Ko-fi and PayPal project-support links.
- GitHub funding configuration.
- Public Docker, configuration, architecture and security-hardening guides.
- `AGENTS.md` guidance for AI-assisted contributors and maintainers.
- Explicit contributor credit for OpenAI Codex as an AI coding contributor.
- Public disclosure that the project is heavily Codex-assisted and vibe-coded by a maintainer who is not a software developer.
- Neutral project branding, reference screenshots, roadmap visual and feature-voting visual.

### Changed

- Docker Compose is now the primary supported deployment path for public self-hosting.
- The recommended first run requires Docker and Docker Compose, but does not require a separately managed host Python environment.
- Compose resource names are project-scoped instead of globally hard-coded, preventing independent checkouts from silently sharing the same database volume.
- The public web bind address is configurable through `RADAR_BIND_ADDRESS`.
- The README and operational documentation now describe the actual release stack and supported lifecycle.
- Backup integrity checking runs inside the application container.
- The Docker image uses the hardened public application factory with authentication abuse protection.
- Public documentation is separated from private deployment-specific operations and infrastructure details.
- Public-facing copy uses Australian English, avoids contractions and avoids em dashes.
- Gunicorn is updated to the 26.x release line.
- `cryptography` is updated to the 50.x release line.
- GitHub Actions and Docker build actions used by the repository are updated to their current supported major releases.

### Fixed

- Restoring a backup now uses a narrowly scoped root maintenance container so an existing database can be replaced safely while normal application services continue to run as the non-root `radar` user.
- Restore returns ownership and permissions to the normal runtime user before restarting the stack.
- Review Queue reference visuals now use deliberate multiline text blocks so release highlights do not collide with action controls.
- Public setup works with the Bash version bundled with macOS as well as modern Linux shells.

### Security

- Real `.env` files, databases, SSH material, backups and runtime data remain excluded from Git.
- Application startup requires a sufficiently strong Flask session secret and valid Fernet encryption key.
- Stored SMTP, Pushover, Portainer and OpenAI-compatible credentials are encrypted before database storage.
- Configurable OpenAI-compatible endpoints are constrained to complete HTTP or HTTPS URLs without embedded credentials.
- Portainer TLS verification is enabled by default.
- Reverse-proxy forwarding headers remain untrusted unless explicitly enabled for one directly connected trusted proxy.
- State-changing browser routes retain CSRF protection.
- Public Docker containers run under the non-root `radar` user.
- SSH Docker probes retain strict host-key checking and a fixed validated inspection command rather than arbitrary remote shell execution.
- Login and password-reset abuse controls use hashed or HMAC-derived rate-limit keys instead of storing raw usernames or client addresses in the rate-limit table.
- Restore preserves a verified pre-restore safety copy before replacing the active database.
- Dependency and static-analysis security checks are part of CI.

### Validated

- The original sanitised v2.6.3 source import passed its publication privacy guard and 56-test regression suite.
- The hardened public candidate passes Python 3.13 compilation and the complete automated test suite in GitHub Actions.
- The public candidate passes `pip-audit` with no ignored dependency advisory.
- The public candidate passes the strict reviewed Bandit gate.
- A clean GitHub Actions runner completes the real `scripts/setup.sh` first-run path, starts all three services, verifies `/healthz` and login, creates an online backup, restores that backup, restarts the Compose stack and confirms persistent state remains healthy.
- A separate clean macOS Docker Desktop acceptance deployment completed successfully and was visually reviewed before version freeze.

---

## [2.6.3] - 2026-08-08

### Changed

- Hardened Portainer service rebinding behaviour for recreated containers and deployment inventory reconciliation.
- Finalised the v2.6.x private production baseline used as the starting source for public-release preparation.

### Fixed

- Corrected final runtime and image version labelling so the deployed release consistently reports v2.6.3.
- Final closeout required no database migration.

### Validated

- Focused Portainer rebinding tests passed.
- The private v2.6.3 candidate passed the automated test suite used at that point in development.

---

## [2.6.2] - 2026-08-08

### Fixed

- Corrected scheduling behaviour for trackers that have never been checked before.
- `is_due(None, 24)` is treated as due rather than being skipped incorrectly.

### Validated

- Added targeted coverage for expired trackers, never-checked trackers and recently checked trackers.

---

## [2.6.1] - 2026-08-07

### Operational Accuracy and Diagnostics

### Changed

- Missing upstream versions are no longer treated as confirmed software updates.
- Checker failures are no longer counted as confirmed updates.
- Unavailable version comparisons are kept separate from genuine update results.

### Added

- A dedicated **Needs Attention** view for operational conditions that require review.
- Separate visibility for checker failures, offline services, unavailable upstream versions and unavailable version comparisons.

---

## Earlier internal releases

Software Release Radar was developed privately before the public GitHub publication. Known internal release milestones include:

- v2.6.0
- v2.3.9
- v2.3.7
- v2.3.4
- v2.2.1
- v2.2.0
- v2.0.2

Detailed historical notes for these internal builds will only be added where they can be reconstructed accurately from retained release records. The public repository will not invent missing historical release notes.

---

## Changelog policy

For public releases:

- user-visible changes belong here;
- security-sensitive details may be delayed until remediation is available;
- deployment-specific private infrastructure details are excluded;
- unreleased work remains under **Unreleased** until a version is tagged; and
- GitHub Releases should link back to the corresponding changelog section.
