# Repository review: October 2026

Review date: 22 October 2026. Baseline: v2.9.3 (`d7aef0c`). Follow-up release: v2.10.0.

This review covers product clarity, release-analysis paths, project documentation and deployment readiness. It is not an exhaustive security audit or a claim of complete image inspection.

## Strengths retained

- Deterministic checking, version comparison, probes, scheduling and standard notifications.
- Existing Portainer/Dockhand inventory and a useful operator-owned upgrade workflow.
- Constrained integrations, encrypted credentials, CSRF controls, bounded AI requests and escaped model output.
- Separate web, scheduler and inventory-worker processes with persistent SQLite state.
- CI for Python tests, dependency auditing, static checks and Docker lifecycle acceptance.

## Addressed in 2.10.0

| Finding | Improvement |
|---|---|
| The README did not clearly explain the upgrade decision benefit or the limits of image analysis. | Added a sourced comparison guide and a concise product overview. |
| The roadmap mixed existing release analysis with future ideas and historical launch checks. | Reorganised it into shipped capabilities, next priorities and exploratory work with acceptance criteria. |
| Application users had no dedicated project revision or roadmap pages. | Added authenticated project pages using the documentation bundled with the running release. |
| Browser and service paths had separate release-context builders and different analysis prompts. | Shared context and prompt definitions to keep the evidence and requested output consistent. |
| Analysis did not explicitly ask about features removed or missed by waiting. | Added those questions and made the evidence limitations explicit. |
| Recorded container image metadata was omitted from the Assistant context. | Added available inventory context with provider checks and freshness caveats, without introducing image pulls or scans. |
| The form-based Assistant path could duplicate a question in the provider request and retain failed turns. | Kept one copy of the question and saved turns only after successful model responses. |
| Untrusted inventory data was introduced into the model context. | Kept supplied evidence below system-policy priority and explicitly labelled all context as untrusted. |
| Long or changing release histories could exceed the request limit or mix a cached target with newer releases. | Bounded the assembled context and anchored the comparison to the tracked target, with incomplete evidence identified. |

## Highest-value remaining gaps

1. **Exact candidate-image identity:** registry digest resolution, platform and configuration comparison are not implemented. A version match alone does not prove which image will be deployed.
2. **Reproducible assessments:** exact source release IDs and completeness metadata are not persisted alongside the analysis. The current lookup has a bounded recent-history window.
3. **Independent security evidence:** there is no SBOM, CVE or signature-verification integration. Release notes and AI summaries cannot substitute for these checks.
4. **Operational visibility:** probe freshness, evidence export and deterministic migration/security signals would make review easier without AI.
5. **Upgrade coverage:** additional cross-version and failure-recovery scenarios would strengthen future schema-changing releases.

The roadmap records these as future work, with image preflight and reproducible comparisons first. No new registry credentials, scanner service or deployment automation was introduced in this release.

## Validation and release discipline

Run the full Python suite and security checks on the final revision, validate the bundled pages in a clean image, and verify the exact deployed version and commit through `/healthz`. CI and release links are the evidence for a particular build; historical README checkmarks are not current certification.

The 2.10.0 changes do not introduce a database schema migration. Preserve the existing configuration, application data, SSH material and a rollback image during deployment.
