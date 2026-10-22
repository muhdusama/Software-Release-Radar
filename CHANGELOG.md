# Changelog

All notable changes to Software Release Radar are documented here.

The project follows semantic versioning for public releases and the Keep a Changelog format.

Format reference: https://keepachangelog.com/en/1.1.0/

## [Unreleased]

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
