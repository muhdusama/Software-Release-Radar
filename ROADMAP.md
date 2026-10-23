# Roadmap

Updated 24 October 2026. Current application version: **2.10.7**.

This timeline shows the intended order of work, not delivery dates. Only Now is available today; future stages may change as we learn from users.

## Now: Review updates with confidence

**Available today.** Connect the versions you run with upstream changes and record an informed upgrade decision.

- Track releases, installed versions and container inventory in one place.
- Review feature gains, removals and what you miss by waiting.
- Record Update, Wait, Ignore or Needs Attention with a maintenance and rollback plan.

### Details

- GitHub release and tag tracking, per-software schedules and installed-version probes.
- Portainer and Dockhand inventory, fleet views and container rebinding.
- Optional Assistant analysis using release notes and recorded image metadata, with bounded context and explicit evidence gaps.
- Upgrade priorities, risk, maintenance dates, checklists, rollback notes and deployment records.
- Email and Pushover notifications with global, personal and per-software preferences.
- In-app contributor credits and AI development disclosure, with roadmap, comparison and revision documentation on GitHub.
- Authenticated access, encrypted integration credentials, CSRF protection and a strict script policy.

The first public release was 2.7.0. The application revision history records delivered changes. Image analysis currently uses inventory metadata and release notes; it does not inspect a proposed image.

## Next: Know exactly which image you would deploy

**Planned.** Exact image preflight connects the update recommendation to the actual container image before you replace a running service.

- Resolve running and candidate images to immutable registry digests.
- Flag mutable-tag rebuilds, unsupported platforms and missing evidence.
- Compare image configuration and runtime requirements without starting the candidate.

### Details

Ready when:

- Both images have a recorded reference, digest, registry, platform and inspection time.
- Unknown or unavailable checks show Needs Attention, never a successful safety check.
- Registry requests remain bounded and credentials follow existing integration controls.
- Configuration differences and runtime requirements can be reviewed before deployment.

## Then: Make every assessment reproducible

**Planned.** Keep the evidence behind an upgrade recommendation so you can revisit it after upstream releases change.

- Save exact release IDs, URLs, version boundaries and completeness information.
- Reach older versions beyond the current 20-record lookup window with bounded pagination.
- Choose a target release and see when its source material changes.

### Details

Ready when a reviewer can reconstruct the evidence behind a saved recommendation. Missing boundaries, incomplete history and truncated notes must remain visible alongside that assessment.

## Later: Make operational checks easier

**Proposed.** Bring freshness, migration signals and decision records into a clearer review workflow, including when AI is disabled.

- Show when probes, inventory and upstream checks were last refreshed.
- Flag documented migrations, removals and security notices with source links.
- Export upgrade decisions and guide common configuration or provider diagnostics.

### Details

Ready when these checks remain useful without AI and text signals are labelled as signals, not guarantees. Cross-version upgrade tests and explicit migration and rollback notices must accompany future data compatibility changes.

## Exploring: Connect more evidence and tools

**Exploratory.** Evaluate additions with the community before committing to implementation.

- Import vulnerability scans, SBOM comparisons and signature or provenance results from established tools.
- Explore more release sources, notification providers and a read-only API.
- Improve fleet filtering, provide a fictional demo and expand deployment and support guidance.

### Details

Supply-chain evidence should include its source and verification time, and connect relevant configuration or migration work to the upgrade plan. A clean scan cannot prove compatibility with a particular deployment.

Integrations will be prioritised by demonstrated demand and maintenance cost. No scanner integration or delivery date is committed. Community work includes documented reverse-proxy examples and a clearer maintenance and support policy as the contributor base grows.

## Principles throughout

Core monitoring stays independent of AI. Deployment remains under your control. New work must preserve authentication, data integrity and constrained access. Release Radar is not an unattended updater, a backup replacement or a general remote-command runner.

## Help shape the next stage

Share a concrete use case, support existing requests with a reaction or discuss trade-offs. Security, reliability and maintenance effort can take priority over votes.

Feature requests: https://github.com/muhdusama/Software-Release-Radar/issues

Discussions: https://github.com/muhdusama/Software-Release-Radar/discussions
