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
| AGPL-3.0 licensing | ✅ Ready | GitHub detects the licence correctly |
| Sanitised application source | 🟡 Pending | Must be imported from the private source repository |
| Clean Docker Compose install | 🟡 Pending | Must be validated on a clean machine |
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

- [ ] Add a clean production-ready `Dockerfile`.
- [ ] Add a public `compose.yaml` or `docker-compose.yml`.
- [ ] Add a safe `.env.example` with useful comments and no secrets.
- [ ] Use persistent volumes or bind mounts for application state.
- [ ] Add health checks where they provide useful failure information.
- [ ] Test `docker compose up -d` on a clean Linux host.
- [ ] Document upgrades, backups and rollback basics.
- [ ] Confirm the container runs the Python 3.13 application without requiring manual host-side Python setup.

### 🧪 Quality and security

- [ ] Add CI for tests and Compose validation.
- [ ] Add dependency scanning.
- [ ] Add code and secret scanning.
- [ ] Run the existing regression suite against the public candidate.
- [ ] Confirm a clean install can reach the application without private environment assumptions.

### 📚 Documentation and visuals

- [ ] Finish installation and configuration guides.
- [ ] Finish architecture documentation against the actual public source tree.
- [ ] Replace reference screenshots with screenshots from the sanitised build.
- [ ] Add an `AGENTS.md` file for AI-assisted contributors and maintainers.
- [ ] Prepare a social preview image for GitHub and external sharing.

### 🚀 Launch gate

The repository only becomes public after the source, privacy, build and installation checks pass.

---

# 🔵 Next: Community-ready foundation

> **Goal:** make the project pleasant to install, understand and contribute to.

<table>
<tr>
<td width="50%" valign="top">

### 🧰 Easier self-hosting

- [ ] Improve first-run setup.
- [ ] Add configuration validation with useful error messages.
- [ ] Provide neutral sample data for evaluation.
- [ ] Add health and readiness diagnostics.
- [ ] Improve migration and upgrade instructions.

</td>
<td width="50%" valign="top">

### 🤝 Better contribution flow

- [ ] Expand automated regression coverage.
- [ ] Add `good first issue` and `help wanted` paths.
- [ ] Document release and maintenance policy.
- [ ] Enable GitHub Discussions for questions and roadmap polls.
- [ ] Keep feature requests structured and easy to vote on.

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
