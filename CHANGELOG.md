# Changelog

All notable changes to Software Release Radar are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to follow semantic versioning for public releases.

## [Unreleased]

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
- Continuous integration for Python compilation, the complete test suite, Docker image builds and clean Compose startup.
- Dependabot configuration for Python, GitHub Actions and Docker dependencies.
- GHCR multi-architecture image publishing workflow.
- Structured GitHub bug report and feature request forms.
- Pull request validation and security checklist.
- Community code of conduct.
- GitHub Discussions and roadmap polling process.
- Buy Me a Coffee, Ko-fi and PayPal project-support links.
- GitHub funding configuration.
- Public configuration guide.
- Public architecture guide.
- Self-hosting security hardening guide.
- Docker installation, backup, restore, upgrade and troubleshooting documentation.
- `AGENTS.md` guidance for AI-assisted contributors and maintainers.
- Explicit contributor credit for OpenAI Codex as an AI coding contributor.
- Public disclosure that the project is heavily Codex-assisted and vibe-coded by a maintainer who is not a software developer.
- Neutral project branding, reference screenshots, roadmap visual and feature-voting visual.

### Changed

- Reworked licensing from the earlier noncommercial publication plan to AGPL-3.0 so the project can be released as genuine open-source software while retaining strong copyleft protections.
- Docker Compose is now the primary supported deployment path for public self-hosting.
- The recommended first run no longer requires Python to be installed or managed on the Docker host.
- The README now describes the actual release-candidate stack instead of the earlier publication scaffold.
- Preview images are displayed at full README width to keep dashboard text readable.
- The roadmap now distinguishes implementation from clean-machine acceptance and keeps public visibility behind explicit launch gates.
- Backup integrity checking now runs inside the application container so host Python is not required.
- The Docker image now uses the hardened public application factory with authentication abuse protection.
- Docker image metadata now declares the project description and AGPL-3.0-only licence.
- Public documentation is separated from private deployment-specific operations and infrastructure details.
- Public-facing copy uses Australian English, avoids contractions and avoids em dashes.

### Security

- Real `.env` files, databases, SSH material, backups and runtime data remain excluded from Git.
- Application startup requires a sufficiently strong Flask session secret and valid Fernet encryption key.
- Stored SMTP, Pushover, Portainer and OpenAI-compatible credentials are encrypted before database storage.
- Portainer TLS verification is enabled by default.
- Reverse-proxy forwarding headers remain untrusted unless explicitly enabled for one directly connected trusted proxy.
- State-changing browser routes retain CSRF protection.
- Public Docker containers run under the non-root `radar` user.
- SSH Docker probes retain strict host-key checking and a fixed validated inspection command rather than arbitrary remote shell execution.
- Login and password-reset abuse controls use hashed/HMAC-derived rate-limit keys rather than storing raw usernames or client addresses in the rate-limit table.
- Restore now preserves a verified pre-restore safety copy before replacing the active database.
- Final public launch still requires a code-freeze privacy scan, secret scan, clean-machine acceptance test and clean public Git history.

### Validation

- Sanitised v2.6.3 source import passed its publication privacy guard.
- The imported baseline passed Python compilation and Git whitespace checks.
- The imported baseline passed the complete 56-test regression suite.
- The imported baseline passed a clean Docker Compose start, `/healthz`, login-page and Portainer-worker smoke test.
- New scheduler, authentication, setup and restore hardening is being validated by the new CI workflow before a public version is frozen.

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
