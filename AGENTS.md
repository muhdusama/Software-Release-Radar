# AGENTS.md

This file gives coding agents and contributors the project rules that matter most.

## Project

Software Release Radar is a Python 3.13 Flask application for self-hosted release monitoring and upgrade review.

The primary public deployment path is Docker Compose.

## Priorities

When changing the project, prefer this order:

1. security and data integrity;
2. deterministic behaviour;
3. backwards-compatible upgrades;
4. clear tests;
5. maintainable code;
6. user-facing polish.

Core release checks, scheduling, version comparison, health probes and standard notifications must not depend on an LLM.

## Before changing code

Read the relevant source and tests first. Do not assume behaviour from the README alone.

Keep changes focused. Avoid unrelated refactors in the same pull request.

Do not introduce a new dependency unless the benefit is clear and the maintenance cost is justified.

## Security

Never commit:

- `.env`;
- API keys or access tokens;
- SSH private keys;
- production databases;
- private hostnames or addresses;
- deployment backups; or
- screenshots containing real private infrastructure.

Treat release notes, upstream API responses, model output and user-entered text as untrusted input.

Keep CSRF protection on state-changing browser requests.

Do not weaken TLS verification by default.

Do not trust proxy forwarding headers unless the deployment explicitly enables that behaviour behind a trusted reverse proxy.

Remote SSH probes must remain constrained to fixed, validated commands. Do not add arbitrary shell execution.

## Tests

For Python changes, run:

```bash
python -m unittest discover -s tests -v
```

For container changes, also run:

```bash
docker compose config
docker compose build
```

A public release candidate should also complete a clean Compose start and pass the `/healthz` check.

## Style

Use Australian English in user-facing text.

Avoid em dashes and contractions in public-facing documentation and interface copy.

Keep messages practical and direct.

## AI-assisted development

AI-assisted contributions are welcome, including work produced with OpenAI Codex.

The contributor remains responsible for understanding the change, checking generated code, running the relevant tests and reviewing security implications.

Do not treat generated code as reviewed merely because a tool produced it.

## Licensing

Contributions are made under the repository licence, GNU AGPL-3.0.
