<p align="center">
  <img src="docs/images/feature-voting-loop.svg" alt="Software Release Radar feature voting process" width="1000">
</p>

# 🗳️ Feature Voting and Roadmap Polling

I want Release Radar to solve problems that people actually have, not just collect a long list of ideas.

Feature voting gives the community a simple way to show what matters most. It is one input into the roadmap, alongside security, reliability, maintenance effort and project fit.

---

## 👍 The simple version

| If you want to... | Do this |
|---|---|
| 💡 Suggest something new | Open a structured feature request |
| 👍 Support an existing idea | Add a thumbs-up reaction to the issue |
| 💬 Add useful context | Comment with your use case or constraints |
| 🗳️ Compare major candidates | Vote in a roadmap poll when one is open |
| 🛠️ Help build it | Say that you are interested in contributing |

Please avoid `+1` comments. A 👍 reaction is easier to count and keeps the discussion readable.

---

## 🔄 How an idea moves through the project

```text
Real problem
    │
    ▼
Feature request
    │
    ▼
Discussion + 👍 reactions
    │
    ▼
Roadmap candidate
    │
    ▼
Roadmap poll, when useful
    │
    ├── Planned
    ├── Needs design or contributor
    ├── Parked
    └── Declined with a reason
    │
    ▼
Implementation
    │
    ▼
Release + changelog
```

---

## 📊 What makes a proposal stronger?

A feature does not need every item below, but these signals make it easier to prioritise.

| Signal | Why it helps |
|---|---|
| 👍 **Community support** | Shows that the problem affects more than one deployment |
| 🎯 **Clear use case** | Makes the need easier to understand and test |
| 🔁 **Reproducible problem** | Separates a general feature from a one-off workaround |
| 🏠 **Good project fit** | Supports self-hosting, privacy, release intelligence or operational clarity |
| 🛡️ **Low operational risk** | Makes the feature safer to adopt |
| ⚙️ **Deterministic design** | Preferred when an LLM is not required |
| 🤝 **Contributor interest** | Makes implementation and long-term maintenance more realistic |
| 🔐 **Security or reliability value** | Important fixes can move ahead of convenience features |

---

## 🗳️ Roadmap polls

Roadmap polls are for comparing credible candidates, not every idea in the issue tracker.

A poll may include 4 to 8 options such as:

- more upstream release sources;
- improved release-note comparison;
- better Docker and Compose discovery;
- more notification providers;
- migration and upgrade tooling;
- read-only API integrations; or
- dashboard and fleet improvements.

When unrelated ideas would make a poll confusing, polls can be grouped by theme.

### Planned public setup

After public launch:

- **GitHub Issues** will hold detailed feature proposals;
- **👍 reactions** will provide a persistent demand signal; and
- **GitHub Discussions polls** will be used for direct roadmap comparisons.

---

## ⚖️ Votes matter, but they are not the only factor

A highly voted feature may still wait when it:

- weakens security or privacy;
- introduces fragile or difficult-to-understand automation;
- creates a large maintenance burden;
- falls outside the scope of Release Radar;
- depends on work that is not ready; or
- is less urgent than a reliability or data-integrity problem.

The reverse is also true. A low-vote security fix may move immediately because protecting existing users is more important than popularity.

---

## 🏷️ Roadmap status guide

| Status | Meaning |
|---|---|
| 💡 **Idea** | Proposed but not yet evaluated |
| 🔎 **Candidate** | Looks useful and is open for stronger community input |
| 🗳️ **Polling** | Included in an active roadmap poll |
| 📌 **Planned** | Accepted for future implementation |
| 🛠️ **In progress** | Actively being worked on |
| ⛔ **Blocked** | Accepted but waiting on a dependency or design decision |
| 💤 **Parked** | Useful idea, but not a current priority |
| ❌ **Declined** | Not planned, with a reason where practical |
| 🚀 **Shipped** | Released and recorded in the changelog |

---

## 📝 Writing a useful feature request

A strong request explains:

- the problem you are trying to solve;
- what you do today instead;
- who would benefit;
- whether it affects Docker, Portainer or another deployment model;
- any privacy or security considerations; and
- what a good result would look like.

**Describe the problem before prescribing the implementation.** There may be a simpler or safer way to solve the same need.

---

## 🔍 Transparency

When a popular feature is not selected, I will aim to explain the reason where practical.

When a roadmap poll changes priorities, the roadmap should be updated so the result is visible in the repository rather than buried in a discussion thread.

---

## 📍 Current state

The first priority is still the safe public release of the v2.6.3 baseline.

Feature voting can collect ideas now, but larger feature work should not displace the privacy, Docker deployment, clean-install, testing and publication checks needed for the first public release.

<p align="center">
  <strong>Next stop:</strong> <a href="ROADMAP.md">view the roadmap</a>
</p>
