# Why Release Radar?

Know what changed before you update. Software Release Radar brings the software you run, upstream changes and your upgrade decision into one place.

## Review the value of an update

An image update can bring useful features, fixes, removed functionality or migration work. Release Radar helps you review that trade-off before replacing a running container:

1. Establish the installed version through a service probe, manual entry or Portainer/Dockhand inventory.
2. Compare it with the tracked GitHub release, using the available release history between the two versions.
3. Review the benefits, removed or deprecated features, compatibility requirements and what you would miss by waiting.
4. Record Update, Wait, Ignore or Needs Attention, with a maintenance date, checklist and rollback notes.
5. Deploy through your existing tools, then record the result in Release Radar.

The optional Release Assistant explains this evidence in plain language. Monitoring, version comparison, probes, scheduling and standard notifications continue to work without AI.

## What image analysis means today

Release Radar uses **running-container inventory metadata and upstream release notes**. When available from a valid inventory mapping, the Assistant can use the recorded image reference, image ID, digest, detected version, state and observation time. A missing digest or stale inventory is a gap to investigate, not proof of safety.

The Assistant is asked to distinguish **features gained**, **features removed or deprecated**, and **what you miss by waiting**, then explain compatibility, migrations, operational checks and its recommendation. These are model interpretations of the supplied evidence, not independently verified guarantees. If upstream notes omit a change, Release Radar cannot reliably infer it.

Release Radar does **not** currently fetch and inspect a candidate image, resolve its registry digest, scan image layers for vulnerabilities, compare SBOMs, verify signatures, test architecture compatibility or run the update in a sandbox. Those checks belong to the proposed image preflight work on the roadmap. It does not deploy or restart your services.

## How it fits alongside other tools

### Diun: image change notifications

Diun watches container image tags and digests and sends notifications when they change. It is useful for detecting registry rebuilds, including changes that do not produce a new application release. Release Radar focuses on installed application versions, upstream release context and the operator's recorded decision. Use a registry watcher alongside Release Radar when digest-only changes matter.

Official documentation: https://crazymax.dev/diun/

### What's Up Docker (WUD): container update monitoring and triggers

WUD watches running containers and their registries, with notification and update triggers. Release Radar adds a release review workflow with benefits, risks, maintenance planning and rollback notes. These are overlapping, complementary tools; the right choice depends on whether your main task is registry monitoring, applying updates or reviewing why to update.

Official documentation: https://getwud.app/

### Renovate: proposed dependency changes in Git

Renovate finds image references in Dockerfiles, Compose files and other manifests, then proposes version or digest changes through pull requests. Release Radar centres the versions detected in your running services and the upgrade decision across your fleet. A Renovate pull request can remain your deployment change while Release Radar holds the operational review.

Official documentation: https://docs.renovatebot.com/docker/

### Trivy: image security inspection

Trivy inspects container images for security findings and can work with SBOMs. Release Radar answers a different part of the decision: which documented features and fixes matter, what may break, and when you intend to update. A release-note summary does not replace an image security scan.

Official documentation: https://trivy.dev/docs/latest/target/container_image/

## Example: is this update worthwhile?

Suppose you run version 1.4 and the tracked release is 1.7. The upstream notes describe a new search feature in 1.5, a reliability fix in 1.6 and a removed authentication option in 1.7.

- **Gain:** the search feature and reliability fix.
- **Potential loss:** the old authentication option, if your deployment uses it.
- **Cost of waiting:** those improvements remain unavailable; any documented security fix also stays unapplied.
- **Decision:** check your authentication configuration and migration instructions before scheduling the update.

This is an illustrative example, not an assessment of a real package. Release Radar should identify missing release notes or an uncertain installed-version mapping instead of making up the missing details.

## Evidence and privacy boundaries

GitHub release history is bounded to the latest 20 returned release records, filtered by the tracker's prerelease setting. Version boundaries that cannot be matched and notes shortened to fit the model request are explicitly identified as incomplete. Tag-only tracking does not provide a complete release-note comparison.

Enabling the optional Assistant sends selected tracker, deployment and release-note context to the OpenAI-compatible endpoint you configure. Review that provider's data handling before using it with private infrastructure. Recommendations remain advisory and require an operator's judgement.

Comparison checked against the linked official documentation on 22 October 2026. Product capabilities can change.
