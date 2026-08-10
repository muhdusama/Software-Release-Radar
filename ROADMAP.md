# Roadmap

Software Release Radar is being prepared for its first public open-source release. This roadmap describes direction rather than fixed delivery dates; priorities may change based on real-world usage, bug reports and contributor feedback.

## Now — Public release readiness

**Goal:** make the existing v2.6.3 application safe, reproducible and understandable for someone who has never seen the original private deployment.

- [ ] Import the sanitised v2.6.3 application source into this repository.
- [ ] Remove private infrastructure names, addresses, credentials, paths and deployment-only operations.
- [ ] Validate a clean Docker Compose deployment from scratch.
- [ ] Add a safe `.env.example` with documented defaults.
- [ ] Add CI for tests and Compose validation.
- [ ] Enable dependency and security scanning.
- [ ] Regenerate final screenshots from a sanitised demo environment.
- [ ] Add `AGENTS.md` for AI-assisted contributors and maintainers.
- [ ] Complete installation, configuration and architecture documentation.
- [ ] Run the final privacy/secret/publication audit.
- [ ] Publish the first GitHub Release only after all launch gates pass.

## Next — Community-ready foundation

**Goal:** make self-hosting and contribution straightforward.

- [ ] Simplify first-run setup and configuration validation.
- [ ] Provide sample/demo data for evaluation without connecting real infrastructure.
- [ ] Add health/readiness diagnostics for common deployment problems.
- [ ] Improve migration and upgrade documentation between releases.
- [ ] Expand automated regression coverage.
- [ ] Add labelled `good first issue` and `help wanted` contribution paths.
- [ ] Establish a documented release and maintenance policy.
- [ ] Add a public support/discussion workflow based on actual community demand.

## Then — Release intelligence

**Goal:** improve the quality of update decisions, not merely the number of sources checked.

- [ ] Expand deterministic version normalisation for unusual release schemes.
- [ ] Improve release-note comparison and change categorisation.
- [ ] Add clearer handling for breaking changes, migrations and security releases.
- [ ] Introduce configurable update policies and maintenance-window hints.
- [ ] Expand source adapters beyond the initial GitHub-centric workflow where there is a strong self-hosting use case.
- [ ] Improve historical release and deployment timelines.

## Later — Fleet and integrations

**Goal:** make Release Radar useful across larger and more varied self-hosted environments.

- [ ] Continue strengthening Portainer inventory and rebinding behaviour.
- [ ] Explore Docker/Compose metadata-based discovery where it can remain predictable and auditable.
- [ ] Add documented integration points for external monitoring and inventory systems.
- [ ] Expand notification providers based on contributor/user demand.
- [ ] Provide a stable API for read-only integrations and automation.

## Exploratory — Assistance without dependency

**Goal:** use AI where interpretation helps while keeping core monitoring deterministic.

Potential areas:

- release-note summarisation;
- upgrade-risk explanation;
- answering questions about tracked releases;
- issue/PR triage for maintainers;
- test generation and review assistance.

Core release checks, scheduling, version comparison, health probes and normal notifications should continue to work without requiring an LLM or external AI service.

## Explicitly not a goal

Software Release Radar is not intended to become:

- an opaque autonomous updater that changes production systems without review;
- dependent on a cloud AI service for basic monitoring;
- a telemetry-heavy service that silently reports private infrastructure data;
- a replacement for backups, configuration management or deployment orchestration.

## How roadmap items move forward

A roadmap item is more likely to move up when it:

1. solves a reproducible problem for multiple users;
2. can be implemented safely and tested deterministically;
3. fits the project's self-hosted and privacy-conscious design;
4. has a contributor willing to help maintain it; or
5. materially improves reliability, security or upgrade decisions.

Suggestions are welcome through GitHub Issues once the repository is public and the contribution workflow is enabled.
