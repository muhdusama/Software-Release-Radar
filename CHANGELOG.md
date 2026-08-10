# Changelog

All notable changes to Software Release Radar are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to follow semantic versioning for public releases.

## [Unreleased]

### Added

- Open-source publication preparation under GNU AGPL-3.0.
- Public-facing README, security policy, contribution guide and support documentation.
- Buy Me a Coffee and PayPal project-support links.
- GitHub funding configuration.
- Public roadmap with visual delivery phases.
- Feature voting and roadmap polling policy.
- Structured GitHub feature request template for community proposals.
- Neutral reference visuals and project branding for the GitHub landing page.
- Visual roadmap and community voting diagrams.
- Clear project identity as a Python 3.13 application intended for Docker Compose deployment.
- `docker-compose.yml` publication scaffold.
- Safe `.env.example` for Docker-level defaults.
- `.gitignore` rules to keep local environment files, runtime data, databases, backups and keys out of Git.
- Docker deployment and clean-host validation guide under `docs/DOCKER.md`.
- Public disclosure that the project is heavily Codex-assisted and vibe-coded by a maintainer who is not a software developer.
- AI-assisted contribution guidance focused on review, testing, security and maintainability.

### Changed

- Reworked licensing from the earlier noncommercial publication plan to AGPL-3.0 so the project can be released as genuine open-source software while retaining strong copyleft protections.
- Redesigned the README to improve visual hierarchy, project discovery, feature explanation and community participation.
- Redesigned the roadmap to make current work, future phases and voting candidates easier to scan.
- Updated the roadmap to distinguish the staged Docker Compose scaffold from the still-pending clean-host deployment validation.
- Public documentation is being separated from private deployment-specific operations and infrastructure details.
- Public-facing copy now uses Australian English, avoids contractions and avoids em dashes.

### Security

- Public release preparation includes a fresh-history publication model, secret and privacy scanning, and regeneration of screenshots using demo data only.
- Real `.env` files remain local and are ignored by Git. Only the safe example file is committed.

---

## [2.6.3] - 2026-08-08

### Changed

- Hardened Portainer service rebinding behaviour for recreated containers and deployment inventory reconciliation.
- Finalised the v2.6.x production baseline used as the source for the first planned public release.

### Fixed

- Corrected final runtime and image version labelling so the deployed release consistently reports v2.6.3.
- Final closeout required no database migration.

### Validated

- Focused Portainer rebinding tests passed.
- Full automated test suite passed with 55 tests during candidate validation.

---

## [2.6.2] - 2026-08-08

### Fixed

- Corrected scheduling behaviour for trackers that have never been checked before.
- `is_due(None, 24)` is now treated as due rather than failing or being skipped incorrectly.

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
