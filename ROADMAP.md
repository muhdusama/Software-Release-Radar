<p align="center">
  <img src="docs/images/roadmap-journey.svg" alt="Software Release Radar roadmap journey" width="1000">
</p>

# 🗺️ Roadmap

Software Release Radar is a public self-hosted project designed so another person can install, understand and operate it without knowing anything about the private environment where it was created.

The first public release is **v2.7.0**. The current public release baseline is **v2.8.0**, with ongoing maintenance active.

<p align="center">
  <a href="#-current-position">📍 Current position</a> ·
  <a href="#-current-ongoing-maintenance-and-community-ready-foundation">🔵 Current</a> ·
  <a href="#-then-better-release-intelligence">🟣 Then</a> ·
  <a href="#-later-fleet-and-integrations">🟠 Later</a> ·
  <a href="#-feature-voting-and-roadmap-polls">🗳️ Vote</a>
</p>

---

## 📍 Current position

| Area | Status | Notes |
|---|---|---|
| Current public release | ✅ v2.8.0 | Current version recorded in `VERSION` and the changelog |
| Sanitised application source | ✅ Passed | Imported without private Gitea history |
| AGPL-3.0 licensing | ✅ Passed | Repository licence is GNU AGPL-3.0 |
| Docker image and Compose stack | ✅ Passed | Web app, automatic scheduler and inventory worker |
| Docker-only first-run setup | ✅ Passed | Tested on a clean GitHub Actions runner and macOS Docker Desktop |
| Automatic release checking | ✅ Passed | Due-only scheduler is part of the standard Compose stack |
| Backup and guarded restore | ✅ Passed | Online backup, integrity checks, safety copy and rollback path tested |
| Authentication hardening | ✅ Passed | Shared login and reset-request throttling |
| Python regression suite | ✅ Passed | Runs on every push and pull request |
| Dependency vulnerability audit | ✅ Passed | `pip-audit` is a blocking CI gate |
| Static security review | ✅ Passed | Bandit gate rejects unexpected high-confidence findings |
| Inventory providers | ✅ Portainer + Dockhand | Provider switching, reconciliation and fail-closed mismatch handling are covered |
| Maintenance dependency baseline | ✅ Current | Gunicorn ≥26.2.0, `cryptography` ≥50.0.1, `regex` ≥2026.9.3 and QEMU action v4.3.0 |
| Clean macOS UX acceptance | ✅ Passed | Clean deployment visually reviewed at normal desktop use |
| Community files and funding | ✅ Passed | Issues, PR template, Discussions, Dependabot and support links |
| v2.7.0 version freeze | ✅ Passed | Historical first-public-release gate |
| Final privacy and secret scan | ✅ Passed | Frozen tracked tree and staging history scanned before public launch |
| Clean public Git history | ✅ Passed | Publication started from a new sanitised root |
| GitHub safety settings | ✅ Launch gate | Applied or reviewed during publication |
| Public launch | ✅ v2.7.0 | First public release |

---

# ✅ What v2.7.0 already proves

<table>
<tr>
<td width="50%" valign="top">

### 🐳 Install and operate

- Docker Compose is the primary deployment path.
- Host Python is not required for the recommended setup.
- The installer creates secure secrets and the first administrator.
- The application waits for health before setup reports success.
- Automatic release checks run without external cron configuration.
- Independent checkouts use isolated Compose resource names.

</td>
<td width="50%" valign="top">

### 💾 Recover safely

- Backups use SQLite's online backup API.
- Backups are integrity checked.
- Restore creates a fresh safety copy first.
- Database writers are stopped during restore.
- Restore returns ownership to the non-root runtime user.
- The full stack is verified healthy before restore reports success.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🔐 Security baseline

- Non-root application containers.
- CSRF protection.
- Encrypted stored integration secrets.
- Login and reset-request throttling.
- Inventory-provider TLS verification enabled by default.
- Reverse-proxy header trust disabled by default.
- Validated OpenAI-compatible HTTP or HTTPS endpoint configuration.
- Strict SSH host-key checking for optional Docker probes.

</td>
<td width="50%" valign="top">

### 🧪 Release gates

- Full Python test suite on GitHub Actions.
- Real public setup lifecycle in CI.
- Backup and restore acceptance in CI.
- Persistent-state restart acceptance.
- `pip-audit` dependency scan.
- Reviewed Bandit static-analysis gate.
- Dependabot for Python, Actions and Docker.
- Version-safe multi-architecture GHCR publishing workflow.

</td>
</tr>
</table>

---

# ✅ v2.7.0 release gates

The first public release was held until the version was consistent, the complete tracked tree and staging history were scanned for private material, the repository was rebuilt from a clean public root, CI passed on that root, the Docker lifecycle passed, backup and restore passed, and a separate macOS Docker Desktop deployment was visually reviewed.

The release process also removes obsolete staging releases and workflow history before the repository changes visibility.

---

# 🔵 Current: Ongoing maintenance and community-ready foundation

> **Goal:** keep the public baseline secure, dependable and easy to operate while learning from real users.

<table>
<tr>
<td width="50%" valign="top">

### 🧰 Reliable self-hosting

- [x] Support both Portainer and Dockhand inventory providers.
- [x] Keep dependency and GitHub Action updates behind the full CI gate.
- [ ] Optional demo-data mode for evaluation.
- [ ] Better guided diagnostics for common configuration errors.
- [ ] Tested reverse-proxy examples based on community demand.
- [ ] More upgrade testing across public releases.
- [ ] Clearer migration notices when a release requires one.

</td>
<td width="50%" valign="top">

### 🤝 Better community flow

- [ ] Label suitable work as `good first issue` and `help wanted`.
- [ ] Publish a maintenance and release policy after the first public cycle.
- [ ] Use Discussions for questions and roadmap polls.
- [ ] Keep feature requests structured and easy to vote on.
- [ ] Evaluate a disposable public demo once the maintenance cost is understood.

</td>
</tr>
</table>

---

# 🟣 Then: Better release intelligence

> **Goal:** improve the quality of update decisions rather than simply checking more sources.

| Candidate | Why it matters |
|---|---|
| 🔢 **Version normalisation** | Better handling of unusual version schemes and tag formats |
| 📋 **Release-note comparison** | Faster understanding of what changed between installed and latest versions |
| ⚠️ **Breaking-change signals** | Make migrations and high-risk updates easier to spot |
| 🔐 **Security-release context** | Help distinguish routine updates from security-sensitive releases |
| 🗓️ **Maintenance hints** | Better support for update timing and planned maintenance |
| 🧾 **Historical timelines** | Make past release decisions and deployments easier to review |
| 🔌 **More upstream sources** | Expand beyond the initial GitHub-focused model where there is a real use case |

These remain candidates for community voting as real-world usage and demand become clearer.

---

# 🟠 Later: Fleet and integrations

> **Goal:** support larger and more varied self-hosted environments without turning the project into a fragile automation platform.

- [ ] Continue strengthening Portainer and Dockhand inventory, provider parity and container rebinding.
- [ ] Explore Docker and Compose metadata discovery where it remains predictable.
- [ ] Add documented integration points for external monitoring and inventory systems.
- [ ] Add notification providers based on real demand.
- [ ] Provide a stable read-only API for integrations and automation.
- [ ] Improve fleet filtering, grouping and operational views.

---

# ⚪ Explore: Assistance without dependency

> **Goal:** use AI where interpretation is useful while normal monitoring remains deterministic.

Potential areas include release-note summarisation, upgrade-risk explanation, questions about tracked releases, maintainer triage, test generation and review assistance.

Core release checks, scheduling, version comparison, health probes and normal notifications should continue to work without an LLM or external AI service.

---

# 🗳️ Feature voting and roadmap polls

<p align="center">
  <img src="docs/images/feature-voting-loop.svg" alt="Software Release Radar feature voting process" width="1000">
</p>

| Step | What happens |
|---|---|
| 💡 **1. Propose** | A user opens a structured feature request and explains the problem. |
| 👍 **2. Support** | Other users add a thumbs-up reaction if the feature would help them. |
| 🗣️ **3. Discuss** | Useful implementation details, risks and alternatives are worked through. |
| 🗳️ **4. Poll** | Strong candidates can be compared in a GitHub Discussions roadmap poll. |
| 🛠️ **5. Plan** | Work moves into the roadmap when scope and maintenance look sensible. |
| 🚀 **6. Ship** | Completed work appears in a release and the changelog. |

Security, data integrity, reliability and maintenance cost can outrank votes.

Read **[FEATURE_VOTING.md](FEATURE_VOTING.md)** for the full process.

---

# 📊 Candidate feature poll board

| Candidate area | Poll state | Community signal |
|---|---|---|
| More upstream release sources | 💡 Candidate | Open to proposals and demand signals |
| Improved release-note comparison | 💡 Candidate | Open to proposals and demand signals |
| Docker and Compose discovery | 💡 Candidate | Open to proposals and demand signals |
| More notification providers | 💡 Candidate | Open to proposals and demand signals |
| Read-only API and integrations | 💡 Candidate | Open to proposals and demand signals |
| Dashboard and fleet UX | 💡 Candidate | Open to proposals and demand signals |

---

# 🚫 What Release Radar is not trying to become

Software Release Radar is not intended to become:

- an autonomous updater that changes production systems without review;
- dependent on a cloud AI service for basic monitoring;
- a telemetry-heavy service that quietly reports private infrastructure data; or
- a replacement for backups, configuration management or deployment orchestration.

---

# 🧭 How priorities are decided

A roadmap item is more likely to move forward when it solves a reproducible problem for several users, fits the self-hosted and privacy-conscious design of the project, can be tested properly, has a sensible maintenance path, has contributor support, or materially improves reliability, security or update decisions.

Community votes are useful evidence. They are not an automatic promise or deadline.
