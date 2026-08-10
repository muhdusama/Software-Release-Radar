# Feature Voting & Roadmap Polling

Software Release Radar is community-informed, but not roadmap-by-popularity alone.

Feature voting exists to answer two useful questions:

1. **Which problems affect the most users?**
2. **Which improvements should be investigated next?**

Votes are an important signal, but reliability, security, maintainability and project fit still matter.

## How to vote

### While the repository is in private staging

Feature proposals can be created as GitHub Issues. Use a **👍 reaction on the issue itself** to support a proposal.

Please avoid posting `+1` comments. Reactions are easier to count and keep discussion readable.

### After public launch

The preferred model will be:

- **GitHub Issues** for detailed feature proposals and implementation discussion;
- **GitHub Discussions polls** for periodic roadmap prioritisation; and
- **👍 reactions** as the persistent demand signal attached to each proposal.

The maintainer may periodically create a poll containing the strongest roadmap candidates so users can compare priorities directly.

## The feature lifecycle

```text
Idea
  │
  ▼
Feature proposal
  │
  ▼
Community feedback + 👍 reactions
  │
  ▼
Roadmap candidate
  │
  ▼
Roadmap poll
  │
  ├── Planned
  ├── Needs design / contributor
  ├── Parked
  └── Declined with rationale
  │
  ▼
Implementation
  │
  ▼
Release + changelog
```

## What makes a feature more likely to be prioritised?

A proposal becomes stronger when it has several of these signals:

| Signal | Why it matters |
|---|---|
| **Community votes** | Shows that the problem affects more than one deployment |
| **Clear use case** | Makes the problem easier to evaluate and test |
| **Reproducible need** | Distinguishes a general feature from one environment's workaround |
| **Project fit** | Supports self-hosting, privacy, release intelligence or operational clarity |
| **Low operational risk** | Easier to adopt without making update management less safe |
| **Deterministic implementation** | Preferred where an LLM is not necessary |
| **Contributor available** | Features are easier to sustain when someone can help build or maintain them |
| **Security/reliability impact** | Important fixes can outrank more popular convenience features |

## How roadmap polls work

Roadmap polls are intended to compare **credible candidate features**, not every idea ever proposed.

A typical poll may contain 4–8 candidates such as:

- additional release-source adapters;
- improved release-note comparison;
- better Docker/Compose discovery;
- more notification providers;
- migration and upgrade tooling;
- read-only API integrations; or
- dashboard and fleet UX improvements.

Polls may be grouped by theme when comparing unrelated features would be misleading.

## How votes affect the roadmap

Votes influence priority, but they do not create an automatic promise or deadline.

A highly voted feature may still be delayed when:

- it weakens security or privacy;
- it introduces fragile or opaque automation;
- its maintenance burden is disproportionate;
- it conflicts with the project's scope;
- a prerequisite is not ready; or
- another issue has greater reliability or security impact.

Conversely, a low-vote security or data-integrity fix may be implemented immediately.

## Roadmap status labels

The project intends to use the following meanings consistently:

| Status | Meaning |
|---|---|
| **Idea** | Proposed but not yet evaluated |
| **Candidate** | Reasonable fit and open for stronger community signal |
| **Polling** | Included in an active roadmap prioritisation poll |
| **Planned** | Accepted for future implementation |
| **In progress** | Actively being implemented |
| **Blocked** | Accepted but waiting on a dependency or design decision |
| **Parked** | Useful idea, but not currently prioritised |
| **Declined** | Not planned; rationale should be documented |
| **Shipped** | Released and recorded in the changelog |

## Proposing a feature

A useful proposal should explain:

- the problem you are trying to solve;
- what you do today instead;
- who would benefit;
- whether it affects self-hosted, Docker, Portainer or other environments;
- whether there are privacy or security implications; and
- what a successful result would look like.

Please describe the **problem before prescribing the implementation**. Often there is a simpler or safer way to solve the same need.

## Transparency

When a popular feature is not selected, the project should explain why where practical.

When a roadmap poll materially changes priorities, the relevant roadmap section should be updated so the repository reflects the decision rather than leaving results buried in a discussion thread.

## Current state

The first priority remains the safe public release of the existing v2.6.3 baseline. Feature voting can collect demand now, but larger feature work should not displace the privacy, build, clean-install and publication gates required for the first public release.
