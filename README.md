<p align="center">
  <img src="docs/images/software-release-radar-wordmark.svg" alt="Software Release Radar. Know what changed before you update." width="900">
</p>

<p align="center">
  <img alt="Version 2.9.3" src="https://img.shields.io/badge/version-2.9.3-2f81f7">
  <img alt="Python 3.13 application" src="https://img.shields.io/badge/app-Python%203.13-3776AB?logo=python&logoColor=white">
  <img alt="Docker Compose deployment" src="https://img.shields.io/badge/deploy-Docker%20Compose-2496ED?logo=docker&logoColor=white">
  <img alt="AGPL 3.0 licence" src="https://img.shields.io/badge/licence-AGPL--3.0-663399">
  <img alt="AI is optional" src="https://img.shields.io/badge/AI-optional-64748b">
</p>

<p align="center">Developed and maintained by <a href="https://imuverse.com"><strong>IMUVERSE</strong></a></p>

<p align="center">
  <a href="#-quick-start">Quick start</a> ·
  <a href="#-preview">Preview</a> ·
  <a href="#-what-it-does">Features</a> ·
  <a href="#-how-monitoring-works">Monitoring</a> ·
  <a href="#-production-readiness">Readiness</a> ·
  <a href="ROADMAP.md">Roadmap</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="#-support-the-project">Support</a>
</p>

> [!IMPORTANT]
> **Latest release: [v2.9.3](https://github.com/muhdusama/Software-Release-Radar/releases/latest).** This update adds IMUVERSE attribution in the application. Recent v2.9 maintenance fixed a Fleet layout overlap, removed Gunicorn's unused control-socket start-up error and restricted backup file permissions. v2.9 also includes Dockhand inventory, global notification defaults and strengthened integration security. Multi-architecture images are published to GHCR. See the [changelog](CHANGELOG.md).

# 📡 What is Software Release Radar?

Software Release Radar is a self-hosted dashboard for people who run a growing collection of software, such as a homelab or a small fleet of servers, and want one dependable place to see what needs updating.

It watches upstream GitHub releases, detects the versions you actually run (through service probes, SSH Docker inspection or a Portainer or Dockhand inventory), and turns every confirmed difference into an explicit decision: update, wait, ignore or investigate. Email and Pushover alerts tell you when something new lands, and an optional AI assistant can summarise what changed.

<table>
<tr>
<td width="33%" valign="top">

### 🐍 Python application

The application is written in Python 3.13 and served through Gunicorn.

</td>
<td width="33%" valign="top">

### 🐳 Docker deployment

Docker Compose is the primary deployment path. Host Python is not required for the recommended first run.

</td>
<td width="33%" valign="top">

### 🧠 AI is optional

Core monitoring is deterministic. AI can help interpret release notes when wanted.

</td>
</tr>
</table>

---

# 🧒 ELI5

Imagine you run 20 or 30 apps at home, in a homelab, or on your own servers.

Each app gets updates at different times. Without a tool like this, you may need to visit several websites, remember what version you installed, read release notes, work out which server runs each app, and decide whether the update is worth doing.

**Software Release Radar handles the repetitive tracking so you can focus on the decision.**

```text
Software you run
       │
       ▼
Check official upstream releases
       │
       ▼
Compare latest version with your version
       │
       ▼
Add machine, container and health context
       │
       ▼
Put the result in one review queue
       │
       ├── Update
       ├── Wait
       ├── Ignore
       └── Investigate
```

> [!NOTE]
> Release Radar is not an unattended production updater. It is designed to improve the information available before you make a change.

---

# 🚀 Quick start

### Requirements

- Docker Engine or Docker Desktop
- Docker Compose v2
- Git

### Install

```bash
git clone https://github.com/muhdusama/Software-Release-Radar.git
```

```bash
cd Software-Release-Radar
```

```bash
bash scripts/setup.sh
```

The setup helper asks for the first administrator account, generates secure application secrets inside a temporary Docker container, writes a protected `.env`, builds the stack, starts all services and waits for the application to report healthy.

Then open:

```text
http://localhost:9120
```

The administrator password itself is not written to `.env`.

Release tags are also published to GHCR as `ghcr.io/muhdusama/software-release-radar` for `linux/amd64` and `linux/arm64`. See [Use the published image instead of building](docs/DOCKER.md#use-the-published-image-instead-of-building) to skip the local build.

Read **[docs/DOCKER.md](docs/DOCKER.md)** before exposing Release Radar beyond a trusted network.

---

# 🖼️ Preview

Screenshots of v2.9.3. They use fictional demo data only: invented software names, `demo-org/*` repositories and `192.0.2.x` documentation addresses.

### Dashboard

Tracked software, update and attention counts, recent release activity and the decision queue at a glance.

<p align="center">
  <img src="docs/images/screenshot-dashboard.webp" alt="Software Release Radar dashboard showing tracked software, update counts, a 14-day release activity chart and recently updated software" width="1050">
</p>

### Upgrade decisions

Every confirmed update becomes a decision with priority, risk, planned maintenance and checklist progress.

<p align="center">
  <img src="docs/images/screenshot-upgrades.webp" alt="Software Release Radar upgrade decision queue listing releases to review, update or wait on, with priority and risk badges" width="1050">
</p>

### Upgrade plan

Record the decision, maintenance date, notes, a pre-upgrade checklist and rollback context for one release.

<p align="center">
  <img src="docs/images/screenshot-upgrade-decision.webp" alt="Software Release Radar upgrade plan for a major release with decision, priority, risk, notes and a pre-upgrade checklist" width="1050">
</p>

### Fleet

Software grouped by machine, with online, offline, update and attention states and editable display names.

<p align="center">
  <img src="docs/images/screenshot-fleet.webp" alt="Software Release Radar fleet view grouping services by machine with version status and probe actions" width="1050">
</p>

---

# ✨ What it does

| Area | Capability |
|---|---|
| 📡 **Release tracking** | GitHub releases, prereleases and latest tags |
| ⏱️ **Automatic monitoring** | Scheduler checks only trackers whose individual refresh interval is due |
| 🔢 **Version awareness** | Installed, detected and upstream version comparison |
| 🖥️ **Fleet inventory** | Machine, service, container, folder, port and health context with editable display names |
| 🐳 **Portainer or Dockhand** | Inventory and source-name synchronisation with local aliases and resilient container rebinding |
| ✅ **Review workflow** | Update, Wait, Ignore, Deployed and Needs Attention decisions |
| 🩺 **Diagnostics** | Separates real updates from checker failures and unavailable comparisons |
| 🔔 **Notifications** | System-wide, personal, channel and per-software controls for SMTP email and Pushover |
| 🧠 **Optional AI** | OpenAI-compatible release comparison and tracker chat |
| 👥 **Multi-user** | Administrator and standard-user roles |
| 💾 **Data safety** | SQLite WAL mode, online backup helper and guarded restore helper |
| 📦 **Deployment** | Docker Compose with persistent state, plus prebuilt `linux/amd64` and `linux/arm64` images on GHCR |

### 📡 Release intelligence

- Track stable releases, prereleases or latest tags.
- Set a refresh interval per software package.
- Compare upstream releases with installed or detected versions.
- Keep checker failures separate from confirmed updates.
- Handle version schemes that need deterministic normalisation.

### 🖥️ Fleet context

- Associate software with machines and services.
- Record host, port, health and Docker container context.
- Group services by machine.
- Surface online, offline, update and needs-attention states.
- Search and filter larger inventories.
- Edit machine, software and stack or folder display names directly from Fleet.
- Follow renamed inventory-provider environments and services automatically while preserving deliberate local aliases.

### 🐳 Docker inventory providers

Release Radar can discover Docker environments and containers from Portainer or Dockhand. Select a provider under Settings, save its encrypted API credential, test the connection, then synchronise from Inventory. Existing Portainer installations remain selected after upgrade.

Dockhand synchronisation verifies each environment before accepting an empty container list. Offline environments keep their last-known inventory. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for token setup and the current Dockhand API limitation.

### ✅ Upgrade decisions

Release Radar provides an operational review queue rather than an unattended updater. A release can carry priority, risk, maintenance timing, notes, rollback context and deployment history.

### 🧠 Optional Release Assistant

An OpenAI-compatible endpoint can be used for release-note analysis and tracker chat. Core release checking, scheduling, probing, version comparison and standard notifications do not require an AI model.

### 🔔 Notification control

The Notifications page separates password-recovery email from release alerts. An administrator can pause release notifications system-wide, each user can choose a personal default and delivery channels, and individual software trackers can inherit that default, always notify, or remain muted. Muted releases are recorded as skipped so turning alerts back on does not send an unexpected backlog.

---

# ⏱️ How monitoring works

The standard Docker stack contains three long-running services:

```text
Browser
   │
   ▼
Web application ───────────────┐
   │                           │
   ├── SQLite state            │
   ├── GitHub release API      │ shared application data
   ├── optional inventory      │
   └── optional AI             │
                               │
Scheduler ─────────────────────┤
   │                           │
   └── checks due trackers     │
                               │
Inventory worker ──────────────┘
       └── background inventory jobs
```

The scheduler wakes every 60 seconds by default. It does not check every tracker every minute. Each tracker keeps its own refresh interval, and only due trackers are checked.

Automatic monitoring therefore works out of the box without an external cron job.

---

# 💾 Back up and restore

Create a verified online SQLite backup:

```bash
./scripts/backup.sh
```

Restore a verified backup:

```bash
bash scripts/restore.sh ./backups/radar-YYYYMMDD-HHMMSS.db --confirm
```

The backup helper uses SQLite's online backup API and runs `PRAGMA integrity_check`.

The restore helper validates the requested backup, creates a fresh pre-restore safety backup, stops database writers, restores through a narrowly scoped maintenance container, returns ownership to the non-root application user, validates the restored database and confirms that the full stack returns healthy.

See **[docs/DOCKER.md](docs/DOCKER.md)** for the full operational procedure.

---

# 🔐 Security model

The current release includes:

- CSRF protection on state-changing browser routes;
- HTTP-only, same-site session cookies;
- optional secure-only session cookies for HTTPS deployments;
- generated application secrets;
- Fernet encryption for stored integration secrets;
- shared login and password-reset throttling;
- security response headers;
- TLS verification enabled by default for inventory providers;
- proxy forwarding headers disabled unless explicitly enabled;
- OpenAI-compatible endpoints restricted to complete HTTP or HTTPS URLs without embedded credentials;
- a non-root application container user;
- strict SSH host-key checking for optional Docker probes;
- fixed remote Docker inspection rather than arbitrary remote shell execution;
- blocking dependency vulnerability auditing with `pip-audit`;
- a reviewed Bandit static-analysis gate in CI;
- a Content Security Policy that blocks inline script; and
- credential-bearing integration requests that require HTTPS, stay on the same origin across redirects and have bounded response sizes.

Security vulnerabilities should not be posted in public issues. Follow **[SECURITY.md](SECURITY.md)**.

For production hardening guidance, see **[docs/SECURITY-HARDENING.md](docs/SECURITY-HARDENING.md)**.

---

# 🧪 Production readiness

The release candidate is tested as a complete lifecycle, not only as a Docker image build.

| Gate | Status and verification |
|---|---|
| Python compilation and complete automated test suite | ✅ Passed |
| Dependency vulnerability audit | ✅ Passed |
| Reviewed Bandit security gate | ✅ Passed |
| Real public first-run setup on a clean Linux runner | ✅ Passed |
| Web health and login-page acceptance | ✅ Passed |
| Automatic scheduler remains running | ✅ Passed |
| Inventory worker remains running | ✅ Passed |
| Online SQLite backup and integrity check | ✅ Passed |
| Guarded restore and return to healthy state | ✅ Passed |
| Persistent state after Compose restart | ✅ Passed |
| Clean macOS Docker Desktop acceptance | ✅ Passed at v2.9.0 |
| Visual review of clean deployment | ✅ Passed at v2.9.0; v2.9.1 preview screenshots reviewed |
| Final privacy and secret scan after version freeze | ✅ Passed at v2.9.0; v2.9.3 public diff reviewed |

The automated gates run in CI on every pull request and on `main`. The macOS acceptance and full version-freeze gates were last run at v2.9.0; they are not presented as repeated v2.9.3 tests. v2.9.3 also includes fixes from the two merged pull requests and refreshed demo-only documentation screenshots.

The public repository was launched at v2.7.0 from a sanitised, clean Git history after a final GitHub safety-settings review. See **[ROADMAP.md](ROADMAP.md)** for the launch checklist.

---

# 🎛️ Vibe-coded and open about it

Software Release Radar is very much a **vibe-coded project**.

I am not a software developer. I started building this because I had a practical problem in my own self-hosted setup and wanted a better way to solve it.

I have used AI coding assistants heavily, first **OpenAI Codex** and more recently **Anthropic Claude Code**, to help design, write, refactor, test and document the project. I set the direction, decide what the application should do, test it in a real environment, review the results and make the final call on changes.

I am being open about this because contributors should know how the project came together. There may be places where an experienced developer would choose a cleaner pattern or spot something that I missed. If you find one, please open an issue or pull request.

<table>
<tr>
<td width="33%" valign="top">

### 🧭 Human direction

Product decisions, priorities and release decisions stay human-led.

</td>
<td width="33%" valign="top">

### 🤖 AI-assisted

OpenAI Codex and Claude Code have been used extensively for implementation, testing, refactoring, review and documentation.

</td>
<td width="33%" valign="top">

### 🧪 Validation matters

AI-generated code is not treated as reviewed simply because a tool produced it. Tests and release gates still apply.

</td>
</tr>
</table>

---

# 👥 Contributors

<p align="center">
  <img alt="Human led" src="https://img.shields.io/badge/project-human%20led-2f81f7">
  <img alt="OpenAI Codex contributor" src="https://img.shields.io/badge/OpenAI%20Codex-AI%20coding%20contributor-412991?logo=openai&logoColor=white">
  <img alt="Claude Code contributor" src="https://img.shields.io/badge/Claude%20Code-AI%20coding%20contributor-D97757?logo=anthropic&logoColor=white">
</p>

| Contributor | Role |
|---|---|
| [@muhdusama](https://github.com/muhdusama) | Creator and maintainer. Product direction, feature decisions, real-world testing and release decisions. |
| [@KoshiirRa](https://github.com/KoshiirRa) | Human contributor. Dockhand inventory-provider compatibility. |
| **OpenAI Codex** | AI coding contributor. Implementation, refactoring, tests, debugging, documentation and code review assistance. |
| **Claude Code** | AI coding contributor. The v2.9 security, reliability and deployment work, release engineering and documentation. |

AI coding tools are not conventional GitHub contributor accounts. GitHub's contributor graph is based on commit authorship, so they may not appear there as separate accounts.

See **[CONTRIBUTORS.md](CONTRIBUTORS.md)** for more detail.

---

# 🗳️ Help shape the roadmap

<p align="center">
  <img src="docs/images/feature-voting-loop.svg" alt="Feature proposal and roadmap voting process" width="1000">
</p>

To get involved:

1. propose a feature using the structured feature request form;
2. vote with a 👍 reaction on requests that would help you;
3. strong candidates can move into a roadmap poll for direct comparison; and
4. results help guide priority alongside security, reliability and maintenance effort.

<p align="center">
  <a href="FEATURE_VOTING.md"><strong>📊 Read how feature voting works</strong></a>
  &nbsp;&nbsp;•&nbsp;&nbsp;
  <a href="ROADMAP.md"><strong>🗺️ View the roadmap</strong></a>
</p>

---

# 🔓 Open-source licence

Software Release Radar is licensed under the **GNU Affero General Public License v3.0 (`AGPL-3.0`)**.

AGPL-3.0 permits use, modification, distribution and commercial use while applying strong copyleft requirements. Covered modifications and derivative works must remain under AGPL-3.0. If a modified version is provided to users over a network, those users must be offered access to the corresponding source code under the licence.

- [Full licence](LICENSE)
- [Commercial use and AGPL obligations](COMMERCIAL_USE.md)
- [Security policy](SECURITY.md)
- [Contribution guide](CONTRIBUTING.md)

---

# ☕ Support the project

Software Release Radar is a side project I am building and maintaining while I look for my next role. If it saves you time or is useful in your environment, any support is appreciated and helps me keep improving it.

<p align="center">
  <a href="https://buymeacoffee.com/muhdusama"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-Support-FFDD00?logo=buymeacoffee&logoColor=000000" alt="Support on Buy Me a Coffee"></a>
  <a href="https://www.paypal.com/paypalme/muhdusama"><img src="https://img.shields.io/badge/PayPal-Donate-003087?logo=paypal&logoColor=white" alt="Donate with PayPal"></a>
</p>

Financial support is optional. The project remains available under its open-source licence either way.

---

# 📚 Documentation

| | Document | What it is for |
|---|---|---|
| 🐳 | [Docker deployment](docs/DOCKER.md) | Install, back up, restore, upgrade and troubleshoot |
| ⚙️ | [Configuration](docs/CONFIGURATION.md) | Environment variables and optional integrations |
| 🔔 | [Notification controls](docs/NOTIFICATIONS.md) | Global, personal, channel and per-software alert policy |
| 🏗️ | [Architecture](docs/ARCHITECTURE.md) | Runtime services, data flow and design boundaries |
| 🔐 | [Security hardening](docs/SECURITY-HARDENING.md) | Production deployment checklist |
| 🗺️ | [Roadmap](ROADMAP.md) | Launch gates and future direction |
| 📜 | [Changelog](CHANGELOG.md) | Release history |
| 🗳️ | [Feature voting](FEATURE_VOTING.md) | How feature requests and roadmap polls work |
| 🤝 | [Contributing](CONTRIBUTING.md) | Contribution and validation workflow |
| 🛡️ | [Security policy](SECURITY.md) | How to report vulnerabilities |
| ☕ | [Support](SUPPORT.md) | Project support and funding options |

---

<p align="center">
  <img src="docs/images/software-release-radar-logo.svg" alt="Software Release Radar logo" width="96">
</p>

<p align="center"><strong>Track releases. Compare versions. Know what changed.</strong></p>

<p align="center">Developed and maintained by <a href="https://imuverse.com">IMUVERSE</a> · <a href="https://imuverse.com">imuverse.com</a></p>
