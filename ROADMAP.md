<p align="center">
  <img src="docs/images/roadmap-journey.svg" alt="Software Release Radar roadmap journey" width="1000">
</p>

# 🗺️ Roadmap

Software Release Radar is moving from a private production tool to a public open-source project that another person should be able to install, understand and rely on without knowing anything about the environment where it was created.

The first public release will not be published until the installation and operational experience is proven from a clean machine.

<p align="center">
  <a href="#-now-release-candidate-hardening">🟢 Now</a> ·
  <a href="#-next-community-ready-foundation">🔵 Next</a> ·
  <a href="#-then-better-release-intelligence">🟣 Then</a> ·
  <a href="#-later-fleet-and-integrations">🟠 Later</a> ·
  <a href="#-explore-assistance-without-dependency">⚪ Explore</a> ·
  <a href="#-feature-voting-and-roadmap-polls">🗳️ Vote</a>
</p>

---

## 📍 Current position

| Area | Status | Notes |
|---|---|---|
| Sanitised application source | ✅ Complete | Imported without the private Gitea history |
| AGPL-3.0 licensing | ✅ Complete | Repository licence is GNU AGPL-3.0 |
| Docker image and Compose stack | ✅ Implemented | Web app, automatic scheduler and Portainer worker |
| Earlier v2.6.3 regression baseline | ✅ Passed | 56 tests and clean Compose smoke test passed before source import |
| Automatic release checking | 🧪 Validation | Scheduler implemented with due-only checking |
| First-run setup | 🧪 Validation | Docker-only setup helper supports Linux and stock macOS Bash |
| Backup and restore | 🧪 Validation | Online backup, integrity check, pre-restore safety backup and rollback path |
| Authentication hardening | 🧪 Validation | Shared login and reset-request throttling added |
| Continuous integration | 🧪 Validation | Python test and clean Docker smoke jobs now run on pushes and pull requests |
| Public configuration and security docs | ✅ Implemented | Docker, configuration, architecture and hardening guides |
| Final privacy and secret scan | ⏳ Pending | Run after code freeze |
| Final screenshots | ⏳ Pending | Must come from a clean demo deployment |
| Clean-machine acceptance test | ⏳ Pending | Required before version freeze and launch |
| Public launch | 🔒 Not yet | Repository stays private until every launch gate passes |

---

# 🟢 Now: Release candidate hardening

> **Goal:** a new user can clone the repository, run the documented setup, sign in, track software, receive automatic checks, back up the database, restore it, upgrade it and troubleshoot normal failures without private knowledge from the original deployment.

## ✅ Completed foundation

### Source and privacy

- [x] Import the sanitised Python application source.
- [x] Exclude private deployment history and environment-specific operational scripts.
- [x] Remove private infrastructure defaults from the public source candidate.
- [x] Use public-safe branding and reference visuals.
- [x] Keep runtime databases, `.env`, SSH material and backups out of Git.

### 🐳 Docker deployment

- [x] Add the production application `Dockerfile`.
- [x] Run the application as a non-root container user.
- [x] Add health checking.
- [x] Add persistent SQLite storage.
- [x] Add a dedicated automatic release scheduler.
- [x] Add a background Portainer worker.
- [x] Add Docker-only first-run setup.
- [x] Add Docker-only online backup with SQLite integrity checking.
- [x] Add guarded restore with a pre-restore safety backup and rollback path.
- [x] Document normal installation, logs, upgrades and troubleshooting.

### 🔐 Application hardening

- [x] Require strong generated application secrets.
- [x] Encrypt stored integration credentials.
- [x] Keep Portainer TLS verification enabled by default.
- [x] Make reverse-proxy header trust opt-in.
- [x] Keep CSRF protection on state-changing browser requests.
- [x] Add shared login throttling across Gunicorn workers.
- [x] Add password-reset request throttling without account enumeration.
- [x] Keep optional SSH probing constrained to validated, fixed Docker inspection commands.

### 🤝 Repository foundation

- [x] Add CI for Python tests and clean Docker Compose startup.
- [x] Add Dependabot.
- [x] Add structured bug and feature request forms.
- [x] Add a pull request checklist.
- [x] Add a code of conduct.
- [x] Add funding options for Buy Me a Coffee, Ko-fi and PayPal.
- [x] Add Discussions for questions and roadmap polling.
- [x] Add a GHCR container publishing workflow.

## ⏳ Remaining launch gates

These are not optional polish items. The repository stays private until they are complete.

### 1. CI must be green on the frozen candidate

- [ ] Complete Python test suite passes on GitHub Actions.
- [ ] Fresh Docker build passes on GitHub Actions.
- [ ] Fresh three-container Compose stack becomes healthy.
- [ ] Scheduler remains running.
- [ ] Portainer worker remains running.
- [ ] Login page and health endpoint pass the smoke test.

### 2. Clean-machine acceptance test

Run the exact public instructions on a machine or isolated environment that does not contain the private production deployment.

- [ ] Fresh clone.
- [ ] `bash scripts/setup.sh` completes without manual repair.
- [ ] First administrator can sign in.
- [ ] Add a real public GitHub tracker.
- [ ] Baseline is created without a false update notification.
- [ ] Scheduler performs a due check automatically.
- [ ] Application survives `docker compose restart` with state retained.
- [ ] Backup helper creates a valid database backup.
- [ ] Restore helper restores a known test state successfully.
- [ ] Upgrade procedure works from the release candidate checkout.
- [ ] Uninstall warning clearly protects the named data volume.

### 3. Security and privacy freeze

- [ ] Run the final secret scan after code freeze.
- [ ] Run the final private identifier and private infrastructure scan.
- [ ] Review every tracked file added since the original sanitisation pass.
- [ ] Verify GitHub private vulnerability reporting.
- [ ] Verify secret scanning and push protection where available.
- [ ] Configure appropriate protection for the public default branch.

### 4. Final launch presentation

- [ ] Seed a clean demo deployment with neutral data.
- [ ] Capture real Dashboard, Review Queue and Fleet screenshots from that build.
- [ ] Replace reference mock-ups with the real screenshots.
- [ ] Prepare a GitHub social preview image.
- [ ] Confirm support links render in the repository Sponsor interface.
- [ ] Make the README release status accurate and remove private-candidate warnings.

### 5. Version and history freeze

The current `v2.6.3` tag represents the earlier private production baseline. Main now contains meaningful new public-release functionality such as automatic scheduling, setup, restore, CI and authentication hardening.

- [ ] Choose the first public version after the candidate is frozen. A minor version such as `v2.7.0` is the likely fit if no breaking change is introduced.
- [ ] Update `VERSION`, application version, Docker defaults, README badges and release notes together.
- [ ] Re-run all acceptance tests against that exact version.
- [ ] Rewrite the private GitHub staging history into one clean public root before visibility changes so obsolete staging and earlier licence experiments are not exposed.
- [ ] Create the public release and GHCR package only from the final clean history.

---

# 🔵 Next: Community-ready foundation

> **Goal:** make Release Radar easier to evaluate and contribute to after the first stable public release.

<table>
<tr>
<td width="50%" valign="top">

### 🧰 Easier self-hosting

- [ ] Add an optional demo-data mode for evaluation.
- [ ] Improve configuration validation where real users encounter confusing failures.
- [ ] Add more guided diagnostics to the UI.
- [ ] Publish tested reverse-proxy examples based on community demand.
- [ ] Expand upgrade testing across public releases.

</td>
<td width="50%" valign="top">

### 🤝 Better community flow

- [ ] Label suitable issues as `good first issue` and `help wanted`.
- [ ] Document the release and maintenance policy after the first public cycle.
- [ ] Use Discussions for questions and roadmap polls.
- [ ] Keep feature requests structured and easy to vote on.
- [ ] Evaluate a disposable public demo when maintenance cost is understood.

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

These are candidates for community voting after the first public release is stable.

---

# 🟠 Later: Fleet and integrations

> **Goal:** support larger and more varied self-hosted environments without turning the project into a fragile automation platform.

- [ ] Continue strengthening Portainer inventory and container rebinding.
- [ ] Explore Docker and Compose metadata discovery where it remains predictable.
- [ ] Add documented integration points for external monitoring and inventory systems.
- [ ] Add notification providers based on real demand.
- [ ] Provide a stable read-only API for integrations and automation.
- [ ] Improve fleet filtering, grouping and operational views.

---

# ⚪ Explore: Assistance without dependency

> **Goal:** use AI where interpretation is useful while normal monitoring remains deterministic.

Potential areas include:

- release-note summarisation;
- upgrade-risk explanation;
- questions about tracked releases;
- maintainer issue and pull request triage;
- test generation; and
- review assistance.

Core release checks, scheduling, version comparison, health probes and normal notifications should continue to work without an LLM or external AI service.

---

# 🗳️ Feature voting and roadmap polls

<p align="center">
  <img src="docs/images/feature-voting-loop.svg" alt="Software Release Radar feature voting process" width="1000">
</p>

The roadmap should reflect real user needs, but popularity is not the only factor.

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
| More upstream release sources | 💤 Not open yet | Opens after public launch |
| Improved release-note comparison | 💤 Not open yet | Opens after public launch |
| Docker and Compose discovery | 💤 Not open yet | Opens after public launch |
| More notification providers | 💤 Not open yet | Opens after public launch |
| Read-only API and integrations | 💤 Not open yet | Opens after public launch |
| Dashboard and fleet UX | 💤 Not open yet | Opens after public launch |

---

# 🚫 What Release Radar is not trying to become

Software Release Radar is not intended to become:

- an autonomous updater that changes production systems without review;
- dependent on a cloud AI service for basic monitoring;
- a telemetry-heavy service that quietly reports private infrastructure data; or
- a replacement for backups, configuration management or deployment orchestration.

---

# 🧭 How priorities are decided

A roadmap item is more likely to move forward when it:

1. solves a reproducible problem for several users;
2. fits the self-hosted and privacy-conscious design of the project;
3. can be implemented safely and tested properly;
4. has a clear maintenance path;
5. has a contributor willing to help; or
6. materially improves reliability, security or update decisions.

Community votes are useful evidence. They are not an automatic promise or deadline.
