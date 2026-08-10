<p align="center">
  <img src="docs/images/roadmap-journey.svg" alt="Software Release Radar roadmap journey" width="1000">
</p>

# 🗺️ Roadmap

Software Release Radar is moving from a private production tool to a public open-source project.

This roadmap shows direction rather than fixed delivery dates. Priorities can change when there is a security issue, a reliability problem, strong community demand, or a contributor ready to help.

<p align="center">
  <a href="#-now-public-release-readiness">🟢 Now</a> ·
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
| v2.6.3 production baseline | ✅ Ready | Existing private application baseline |
| Public documentation | 🟢 In progress | README, roadmap, changelog, security and contribution material |
| Public-safe visuals | ✅ Ready | Logo, wordmark and neutral reference screenshots |
| Build approach disclosure | ✅ Ready | README explains the project is Codex-assisted and vibe-coded |
| AGPL-3.0 licensing | ✅ Ready | GitHub detects the licence correctly |
| Docker Compose scaffold | ✅ Staged | `docker-compose.yml`, `.env.example`, `.gitignore` and Docker guide are present |
| Sanitised application source | 🟡 Pending | Must be imported from the private source repository |
| Clean Docker Compose install | 🟡 Pending | Must be validated after the source and Dockerfile are staged |
| CI and security checks | 🟡 Pending | Added after the application source is staged |
| Public launch | 🔒 Not yet | Repository stays private until the release gates pass |

---

# 🟢 Now: Public release readiness

> **Goal:** make v2.6.3 safe, reproducible and easy to understand for someone who has never seen the original environment.

### Source and privacy

- [ ] Import the sanitised v2.6.3 application source.
- [ ] Remove private infrastructure names, addresses, paths and deployment-only scripts.
- [ ] Run a full secret and privacy scan.
- [ ] Confirm that no production screenshots or runtime data are present.
- [ ] Start the public code history from the sanitised source rather than the old private Git history.

### 🐳 Docker deployment

**Primary public deployment method: Docker Compose.**

- [ ] Add a clean production-ready `Dockerfile` after the source is imported.
- [x] Add a public `docker-compose.yml`.
- [x] Add a safe `.env.example` with useful comments and no secrets.
- [x] Add `.gitignore` rules for `.env`, runtime data, databases, backups and keys.
- [x] Add a persistent data mount to the Compose scaffold.
- [x] Add a Docker deployment and validation guide.
- [ ] Confirm the application-specific environment variables against the sanitised source.
- [ ] Add health checks where they provide useful failure information.
- [ ] Test `docker compose up -d --build` on a clean Linux host.
- [ ] Validate restart with persistent state retained.
- [ ] Document final upgrade, backup and rollback procedures.
- [ ] Confirm the container runs the Python 3.13 application without requiring manual host-side Python setup.

### 🧪 Quality and security

- [ ] Add CI for tests and Compose validation.
- [ ] Add dependency scanning.
- [ ] Add code and secret scanning.
- [ ] Run the existing regression suite against the public candidate.
- [ ] Confirm a clean install can reach the application without private environment assumptions.

### 📚 Documentation and launch presentation

- [x] Explain clearly that the application is Python and Docker is the deployment layer.
- [x] Document the Codex-assisted, vibe-coded origin of the project.
- [x] Add Docker quick-start scaffolding without presenting it as already validated.
- [ ] Finish installation and configuration guides against the actual public source.
- [ ] Finish architecture documentation against the actual public source tree.
- [ ] Replace reference screenshots with screenshots from the sanitised build.
- [ ] Add an `AGENTS.md` file for AI-assisted contributors and maintainers.
- [ ] Prepare a social preview image for GitHub and external sharing.
- [ ] Add a concise repository description and focused GitHub topics.
- [ ] Make the first public release page useful on its own, with screenshots, highlights and upgrade notes.

### 🚀 Launch gate

The repository only becomes public after the source, privacy, build and installation checks pass.

---

# 🔵 Next: Community-ready foundation

> **Goal:** make the project pleasant to install, understand, discover and contribute to.

<table>
<tr>
<td width="50%" valign="top">

### 🧰 Easier self-hosting

- [ ] Improve first-run setup.
- [ ] Add configuration validation with useful error messages.
- [ ] Provide neutral sample data for evaluation.
- [ ] Add health and readiness diagnostics.
- [ ] Improve migration and upgrade instructions.
- [ ] Add a simple demo mode that does not require real infrastructure data.

</td>
<td width="50%" valign="top">

### 🤝 Better community flow

- [ ] Expand automated regression coverage.
- [ ] Add `good first issue` and `help wanted` paths.
- [ ] Document release and maintenance policy.
- [ ] Enable GitHub Discussions for questions and roadmap polls.
- [ ] Keep feature requests structured and easy to vote on.
- [ ] Evaluate a disposable public demo once the first release is stable.

</td>
</tr>
</table>

### 🔎 Make the project easier to find

Successful self-hosted projects usually make the purpose obvious within seconds and give visitors a fast path to try, install, follow or support the project. Release Radar should do the same without adding unnecessary marketing clutter.

- [ ] Use focused GitHub topics such as `self-hosted`, `docker`, `docker-compose`, `python`, `homelab`, `release-monitoring`, `version-tracking`, `portainer` and `devops`.
- [ ] Keep the first screenshot and one-line purpose near the top of the README.
- [ ] Replace the staging Docker warning with a tested quick-start section after clean-host validation.
- [ ] Enable Discussions and keep questions out of bug reports where practical.
- [ ] Add contributor and project-activity sections once there is real public activity to show.
- [ ] Add a star-history view only after the repository has meaningful public history.

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

These items are strong candidates for community voting once the first public release is stable.

---

# 🟠 Later: Fleet and integrations

> **Goal:** support larger and more varied self-hosted environments without turning the project into a fragile automation platform.

- [ ] Continue strengthening Portainer inventory and container rebinding.
- [ ] Explore Docker and Compose metadata discovery where it remains predictable.
- [ ] Add documented integration points for external monitoring and inventory systems.
- [ ] Add more notification providers based on real demand.
- [ ] Provide a stable read-only API for integrations and automation.
- [ ] Improve fleet filtering, grouping and operational views.

---

# ⚪ Explore: Assistance without dependency

> **Goal:** use AI where interpretation is useful while keeping normal monitoring deterministic.

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

### How voting will work

| Step | What happens |
|---|---|
| 💡 **1. Propose** | A user opens a structured feature request and explains the problem. |
| 👍 **2. Support** | Other users add a thumbs-up reaction if the feature would help them. |
| 🗣️ **3. Discuss** | Useful implementation details, risks and alternatives are worked through. |
| 🗳️ **4. Poll** | Strong candidates can be compared in a GitHub Discussions roadmap poll. |
| 🛠️ **5. Plan** | The selected work moves into the roadmap when scope and maintenance look sensible. |
| 🚀 **6. Ship** | Completed work appears in a release and the changelog. |

### What can outrank votes?

A popular feature may still wait if it creates a security problem, weakens privacy, adds a large maintenance burden, or depends on work that is not ready.

A less popular reliability or data-integrity fix may move ahead quickly because it protects existing users.

Read **[FEATURE_VOTING.md](FEATURE_VOTING.md)** for the full process.

---

# 📊 Candidate feature poll board

This table will become a live summary of the strongest community candidates after public launch.

| Candidate area | Poll state | Community signal |
|---|---|---|
| More upstream release sources | 💤 Not open yet | Opens after public launch |
| Improved release-note comparison | 💤 Not open yet | Opens after public launch |
| Docker and Compose discovery | 💤 Not open yet | Opens after public launch |
| More notification providers | 💤 Not open yet | Opens after public launch |
| Read-only API and integrations | 💤 Not open yet | Opens after public launch |
| Dashboard and fleet UX | 💤 Not open yet | Opens after public launch |

When polls open, this section should link directly to them so visitors do not need to search through Issues or Discussions.

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

---

<p align="center">
  <strong>Have an idea?</strong><br>
  Read <a href="FEATURE_VOTING.md">Feature Voting</a>, then use the feature request form when the repository opens to the public.
</p>
