<p align="center">
  <img src="docs/images/software-release-radar-wordmark.svg" alt="Software Release Radar. Know what changed before you update." width="900">
</p>

<p align="center">
  <img alt="Version 2.6.3" src="https://img.shields.io/badge/version-2.6.3-2f81f7">
  <img alt="Python 3.13 application" src="https://img.shields.io/badge/app-Python%203.13-3776AB?logo=python&logoColor=white">
  <img alt="Docker Compose deployment" src="https://img.shields.io/badge/deploy-Docker%20Compose-2496ED?logo=docker&logoColor=white">
  <img alt="AGPL 3.0 licence" src="https://img.shields.io/badge/licence-AGPL--3.0-663399">
  <img alt="AI is optional" src="https://img.shields.io/badge/AI-optional-64748b">
</p>

<p align="center">
  <a href="#-quick-start">Quick start</a> ·
  <a href="#-preview">Preview</a> ·
  <a href="#-what-it-does">Features</a> ·
  <a href="#-how-monitoring-works">Monitoring</a> ·
  <a href="#-vibe-coded-and-open-about-it">How it was built</a> ·
  <a href="ROADMAP.md">Roadmap</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="#-support-the-project">Support</a>
</p>

> [!CAUTION]
> **Private release candidate.** The sanitised application source, Dockerfile and Compose stack are now in this repository. The earlier 56-test regression suite and clean Compose smoke test passed before the source import. Additional production-readiness work is still being validated on `main`, including the automatic scheduler, CI, restore workflow, final security checks and real demo screenshots. The repository will remain private until those gates pass.

# 📡 What is Software Release Radar?

Software Release Radar is a self-hosted dashboard for people who run a growing collection of software and want a better way to keep track of updates.

It checks upstream releases, compares them with the versions you run, adds machine and service context, and gives you one place to decide what should be updated, delayed, ignored or investigated.

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

> [!IMPORTANT]
> Release Radar is not designed to blindly update production systems. The goal is to give you better information before you make the change.

---

# 🚀 Quick start

### Requirements

- Docker Engine or Docker Desktop
- Docker Compose v2
- Git

### Install

```bash
git clone https://github.com/muhdusama/Software-Release-Radar.git
cd Software-Release-Radar
bash scripts/setup.sh
```

The first-run helper creates secure application secrets inside a temporary Docker container, writes a protected `.env`, builds the stack, starts it and waits for the web application to report healthy.

Then open:

```text
http://localhost:9120
```

No administrator password is stored in plaintext.

Read **[docs/DOCKER.md](docs/DOCKER.md)** before exposing Release Radar beyond a trusted network.

---

# 🖼️ Preview

> These are public-safe reference visuals made with neutral demo data. They are not captures of a private production environment. They will be replaced by final screenshots from a clean demo deployment before the repository is made public.

### Dashboard

<p align="center">
  <img src="docs/images/reference-dashboard.svg" alt="Software Release Radar dashboard reference screenshot" width="1050">
</p>

### Review queue

<p align="center">
  <img src="docs/images/reference-review-queue.svg" alt="Software Release Radar review queue reference screenshot" width="1050">
</p>

### Fleet

<p align="center">
  <img src="docs/images/reference-fleet.svg" alt="Software Release Radar fleet reference screenshot" width="1050">
</p>

---

# ✨ What it does

| Area | Capability |
|---|---|
| 📡 **Release tracking** | GitHub releases, prereleases and latest tags |
| ⏱️ **Automatic monitoring** | Scheduler checks only trackers whose individual refresh interval is due |
| 🔢 **Version awareness** | Installed, detected and upstream version comparison |
| 🖥️ **Fleet inventory** | Machine, service, container, port and health context |
| 🐳 **Portainer** | Inventory synchronisation and resilient container rebinding |
| ✅ **Review workflow** | Update, Wait, Ignore, Deployed and Needs Attention decisions |
| 🩺 **Diagnostics** | Separates real updates from checker failures and unavailable comparisons |
| 🔔 **Notifications** | SMTP email and Pushover delivery |
| 🧠 **Optional AI** | OpenAI-compatible release comparison and tracker chat |
| 👥 **Multi-user** | Administrator and standard-user roles |
| 💾 **Data safety** | SQLite WAL mode, online backup helper and guarded restore helper |
| 📦 **Deployment** | Docker Compose with persistent state |

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

### ✅ Upgrade decisions

Release Radar provides an operational review queue rather than an unattended updater. A release can carry priority, risk, maintenance timing, notes, rollback context and deployment history.

### 🧠 Optional Release Assistant

An OpenAI-compatible endpoint can be used for release-note analysis and tracker chat. Core release checking, scheduling, probing, version comparison and standard notifications do not require an AI model.

---

# ⏱️ How monitoring works

The Docker stack contains three long-running services:

```text
Browser
   │
   ▼
Web application ───────────────┐
   │                           │
   ├── SQLite state            │
   ├── GitHub release API      │ shared application data
   ├── optional Portainer      │
   └── optional AI             │
                               │
Scheduler ─────────────────────┤
   │                           │
   └── checks due trackers     │
                               │
Portainer worker ──────────────┘
       └── background inventory jobs
```

The scheduler wakes every 60 seconds by default. It does **not** check every tracker every minute. Each tracker keeps its own refresh interval, and only due trackers are checked.

This means automatic monitoring works out of the box without an external cron job.

---

# 🏗️ Architecture

```mermaid
flowchart LR
    U[Browser] --> W[Web application]
    S[Scheduler] --> C[Release checker]
    P[Portainer worker] --> DB[(SQLite)]
    W --> DB
    C --> DB
    C --> GH[GitHub API]
    C --> N[Notifications]
    W --> PT[Portainer API]
    W -. optional .-> AI[OpenAI-compatible API]
```

**Design rule:** deterministic automation first. AI is used for interpretation where it adds value, not as a requirement for basic monitoring.

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

The backup helper uses SQLite's online backup API and runs `PRAGMA integrity_check`. The restore helper validates the backup, stops writers, restores through a one-off container, validates the restored database and starts the stack again.

See **[docs/DOCKER.md](docs/DOCKER.md)** for the full operational procedure.

---

# 🔐 Security model

The public baseline includes:

- CSRF protection on state-changing browser routes;
- HTTP-only, same-site session cookies;
- optional secure-only session cookies for HTTPS deployments;
- generated application secrets;
- Fernet encryption for stored integration secrets;
- security response headers;
- TLS verification enabled by default for Portainer;
- proxy forwarding headers disabled unless explicitly enabled;
- a non-root container user;
- strict SSH host-key checking for optional Docker probes; and
- fixed remote Docker inspection rather than arbitrary remote shell execution.

Security vulnerabilities should not be posted in public issues. Follow **[SECURITY.md](SECURITY.md)**.

---

# 🎛️ Vibe-coded and open about it

Software Release Radar is very much a **vibe-coded project**.

I am not a software developer. I started building this because I had a practical problem in my own self-hosted setup and wanted a better way to solve it.

I have used **OpenAI Codex heavily** to help design, write, refactor, test and document the project. I set the direction, decide what the application should do, test it in a real environment, review the results and make the final call on changes.

I am being open about this because contributors should know how the project came together. There may be places where an experienced developer would choose a cleaner pattern or spot something that I missed. If you find one, please open an issue or pull request.

<table>
<tr>
<td width="33%" valign="top">

### 🧭 Human direction

Product decisions, priorities and release decisions stay human-led.

</td>
<td width="33%" valign="top">

### 🤖 Codex-assisted

Codex has been used extensively for implementation, testing, refactoring and documentation.

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
</p>

| Contributor | Role |
|---|---|
| [@muhdusama](https://github.com/muhdusama) | Creator and maintainer. Product direction, feature decisions, real-world testing and release decisions. |
| **OpenAI Codex** | AI coding contributor. Implementation, refactoring, tests, debugging, documentation and code review assistance. |

Codex is an AI coding tool rather than a conventional GitHub contributor account. GitHub's contributor graph is based on commit authorship, so Codex may not appear there as a separate account.

See **[CONTRIBUTORS.md](CONTRIBUTORS.md)** for more detail.

---

# 🗳️ Help shape the roadmap

<p align="center">
  <img src="docs/images/feature-voting-loop.svg" alt="Feature proposal and roadmap voting process" width="1000">
</p>

Once the repository is public:

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

# 🗺️ Release-candidate status

<p align="center">
  <img src="docs/images/roadmap-journey.svg" alt="Software Release Radar roadmap journey" width="1000">
</p>

| Gate | Status |
|---|---|
| Sanitised application source imported without private Git history | ✅ Passed |
| Earlier full regression suite | ✅ 56 tests passed |
| Earlier clean Docker Compose installation | ✅ Passed |
| Multi-architecture v2.6.3 container build | ✅ Passed |
| Automatic release scheduler | 🧪 Implemented, CI validation in progress |
| CI on every push and pull request | 🧪 Implemented, validation in progress |
| Docker-only first-run setup | 🧪 Implemented, clean-host validation pending |
| Backup and guarded restore workflow | 🧪 Implemented, restore validation pending |
| Dependabot and community templates | ✅ Added |
| Final privacy and secret scan | ⏳ Pending after code freeze |
| Final screenshots from a clean demo deployment | ⏳ Pending |
| Public release version and launch audit | ⏳ Pending |

The repository stays private until the remaining gates pass.

See the full **[Roadmap](ROADMAP.md)** and **[Changelog](CHANGELOG.md)**.

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
  <a href="https://ko-fi.com/muhdusama"><img src="https://img.shields.io/badge/Ko--fi-Support-FF5E5B?logo=kofi&logoColor=white" alt="Support on Ko-fi"></a>
  <a href="https://www.paypal.com/paypalme/muhdusama"><img src="https://img.shields.io/badge/PayPal-Donate-003087?logo=paypal&logoColor=white" alt="Donate with PayPal"></a>
</p>

Financial support is optional. The project remains available under its open-source licence either way.

---

# 📚 Project links

| | Document | What it is for |
|---|---|---|
| 🐳 | [docs/DOCKER.md](docs/DOCKER.md) | Install, configure, back up, restore, upgrade and troubleshoot |
| 🗺️ | [ROADMAP.md](ROADMAP.md) | Current priorities and future direction |
| 📊 | [FEATURE_VOTING.md](FEATURE_VOTING.md) | How community feature voting works |
| 📝 | [CHANGELOG.md](CHANGELOG.md) | Release history and notable changes |
| 👥 | [CONTRIBUTORS.md](CONTRIBUTORS.md) | Project contributor credits |
| 🤝 | [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| 🔐 | [SECURITY.md](SECURITY.md) | Responsible vulnerability reporting |
| 💬 | [SUPPORT.md](SUPPORT.md) | Support channels and project support |
| ⚖️ | [COMMERCIAL_USE.md](COMMERCIAL_USE.md) | Plain-language AGPL guidance |
| 📄 | [LICENSE](LICENSE) | Full AGPL-3.0 licence text |

---

<p align="center">
  <img src="docs/images/software-release-radar-logo.svg" alt="Software Release Radar logo" width="110">
</p>

<p align="center"><strong>Track releases. Compare versions. Know what changed.</strong></p>
