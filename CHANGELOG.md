# Changelog

All notable changes to Software Release Radar are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to follow semantic versioning for public releases.

## [Unreleased]

### Added

- A clearly labelled Global defaults section for inherited software notification behaviour and delivery channels.

### Fixed

- Per-software notification preference changes now save immediately without reloading the Notifications page.
- Bulk software preferences and global notification defaults now save without clearing the current software filter.
- The Notifications software search is retained for the browser session, including after a manual refresh.

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