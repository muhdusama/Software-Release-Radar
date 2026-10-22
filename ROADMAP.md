# Roadmap

Updated 22 October 2026. Current application version: **2.10.0**.

Release Radar is built around a practical question: **is this update worthwhile for the software I actually run?** The roadmap prioritises better evidence for that decision while keeping monitoring deterministic and deployment under operator control.

Items below are separated into shipped capabilities, next priorities and exploratory ideas. Planned items are not available features, delivery promises or scheduled releases.

## Available in 2.10.0

- GitHub release and tag tracking with per-software schedules, installed-version probes and update classification.
- Portainer and Dockhand inventory, fleet views and container rebinding.
- Upgrade decisions with priority, risk, maintenance dates, checklists, rollback notes and deployment records.
- Optional release analysis that asks what you gain, what may be removed and what you miss by waiting, using the available release notes and recorded image context.
- Shared release-comparison context across the browser and service paths, with bounded inputs and explicit evidence gaps.
- In-app About, Revision updates and Roadmap pages, with project documentation packaged in the application image.
- Email and Pushover notifications with global, personal and per-software preferences.
- Authenticated access, encrypted integration credentials, CSRF protection and a strict script policy.

The first public release was 2.7.0. See the revision history for the changes in each release. Historical acceptance results are evidence for their original revisions, not a claim that every later release repeated every manual check.

## Next priority: exact image preflight

**Status: planned; not implemented.**

Resolve the running and proposed container images to immutable registry digests before an update. This would close the largest gap between release-note advice and the artifact you actually deploy.

Acceptance criteria:

- Record the image reference, digest, source registry, platform and inspection time for both versions.
- Identify mutable-tag rebuilds, unsupported architectures and missing evidence.
- Compare relevant image configuration and runtime requirements without starting the candidate image.
- Keep registry access bounded and credential handling consistent with existing integration controls.
- Present unknown or unavailable checks as Needs Attention, never as a successful safety check.

## Next priority: reproducible release comparisons

**Status: planned; current release lookups remain bounded.**

- Persist the exact release IDs, URLs and version boundaries used for each assessment.
- Add bounded pagination for versions older than the current 20-record lookup window.
- Let an operator select a specific target release instead of only the tracked current release.
- Show changes in the source material since a saved assessment.
- Preserve completeness and truncation information with the stored analysis.

Acceptance means a reviewer can reconstruct the evidence behind an old recommendation even after upstream releases change.

## Next priority: clearer operational evidence

**Status: proposed.**

- Deterministic flags for documented migrations, removals and security notices, with links to the relevant source text.
- A visible freshness summary for installed-version probes, inventory and upstream checks.
- Exportable upgrade decision records for change reviews.
- Cross-version upgrade tests and explicit migration and rollback notices when data compatibility changes.
- Guided diagnostics for common configuration and provider failures.

Text signals must be labelled as signals rather than guarantees, and must remain useful when AI is disabled.

## Later: optional supply-chain checks

**Status: exploratory; no scanner integration is shipped.**

- Import results from established vulnerability scanners rather than build a new scanner.
- Compare SBOMs and report package additions, removals and known vulnerability changes.
- Display signature and provenance verification results with their verification source and timestamp.
- Link configuration changes and migration requirements to an upgrade plan.

These checks should complement release analysis. A clean scan cannot prove that an update is compatible with a particular deployment.

## Later: integrations and community

**Status: proposed, prioritised by demonstrated demand.**

- Additional upstream release sources and notification providers.
- A stable read-only API for inventory and upgrade decisions.
- A disposable demo using fictional data.
- More fleet filtering and documented reverse-proxy examples.
- Clear maintenance and support policy as the contributor base grows.

## Product boundaries

Core monitoring must not require an LLM. Release Radar should not become an unattended production updater, a replacement for backups or a general remote-command runner. AI recommendations remain advisory. New integrations must preserve authentication, data integrity and constrained access.

## Help set priorities

Propose a concrete use case in GitHub Issues, support existing requests with a reaction and discuss trade-offs in GitHub Discussions. Security, reliability and maintenance effort can take priority over votes. Accepted and delivered work is recorded in the changelog.

Feature requests: https://github.com/muhdusama/Software-Release-Radar/issues

Discussions: https://github.com/muhdusama/Software-Release-Radar/discussions
