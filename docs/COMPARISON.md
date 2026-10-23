# Compare approaches

Software Release Radar helps you decide whether an update is worthwhile for the software you actually run. It connects installed versions, upstream changes and your upgrade plan in one place.

## Review the value of an update

The focus is your decision before deployment. Start with the installed version, review the available evidence, then record Update, Wait, Ignore or Needs Attention.

### What will I gain?

See the documented features, fixes and improvements between your installed version and the tracked release.

### What could I lose?

Look for removed features, deprecated settings and changed behaviour that could affect your deployment.

### What if I wait?

Understand which improvements and fixes remain unavailable on your current version.

### What needs preparation?

Review compatibility and migrations, then record a maintenance window, checklist and rollback plan.

## What image analysis means today

The optional Assistant interprets supplied evidence and identifies uncertainty. Monitoring, version comparison, probes, scheduling and standard notifications work without AI.

### Available today

Recorded running-container metadata from a valid inventory mapping: image reference, image ID, digest, detected version, state and observation time. GitHub release notes provide the context for feature gains, removals and the cost of waiting. Organizr v2 uses its official version-history feed.

Missing metadata and incomplete notes remain evidence gaps. The Assistant cannot reliably infer changes that upstream notes omit.

### On the roadmap

Exact candidate-image inspection, registry digest resolution, platform and configuration comparison, and optional security evidence from established tools.

Release Radar does not currently pull or run a candidate image, scan its layers, compare SBOMs or verify signatures. Deployment stays under your control.

## Great projects to explore

Diun, What's Up Docker, Renovate and Trivy are excellent projects. We appreciate their maintainers and encourage you to explore them. Their capabilities can complement Release Radar, and the best combination depends on your workflow.

### Diun

**Image change notifications.** Watches image tags and digests, including registry rebuilds that may not produce an application release.

Use its registry alerts alongside Release Radar's review of application changes and recorded upgrade decisions.

Official documentation: https://crazymax.dev/diun/

### What's Up Docker (WUD)

**Container update monitoring and triggers.** Watches running containers and their registries, with notification and update triggers.

Use WUD for monitoring and triggers alongside Release Radar for benefits, risks, maintenance planning and rollback notes.

Official documentation: https://getwud.app/

### Renovate

**Dependency changes through Git.** Proposes image tag, digest and dependency changes through pull requests.

A Renovate pull request can remain your deployment change while Release Radar holds the review of versions running across your fleet.

Official documentation: https://docs.renovatebot.com/docker/

### Trivy

**Image security evidence.** Inspects container images for security findings and works with SBOMs.

Use its security evidence alongside Release Radar's review of documented features, compatibility and maintenance timing.

Official documentation: https://trivy.dev/docs/latest/target/container_image/

## An update decision in practice

An illustrative example: you run version 1.4 and the target is 1.7. The notes describe new search in 1.5, a reliability fix in 1.6 and a removed authentication option in 1.7.

### Gain

The new search feature and reliability fix.

### Check

Whether your deployment still uses the removed authentication option.

### Wait

Those improvements remain unavailable on the installed version.

### Decide

Review the migration instructions and your configuration before scheduling the update.

## Evidence and privacy

Release history is bounded to 20 upstream version records. Standard repositories use GitHub Releases and the tracker's prerelease setting; Organizr v2 uses its official version-history feed, and SearXNG uses its official `master` commit history. Source commits do not prove that a container image has been published or tested. Missing version boundaries and truncated notes are identified as incomplete. Tag-only tracking does not provide a full release-note comparison.

The optional Assistant sends selected tracker, deployment and release-note context to the OpenAI-compatible endpoint you configure. Review that provider's data handling for private infrastructure. Recommendations remain advisory and require operator judgement.

Comparison checked against the linked official documentation on 22 October 2026. Product capabilities can change.
