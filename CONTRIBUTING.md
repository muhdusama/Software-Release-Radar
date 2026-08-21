# 🤝 Contributing

Contributions that improve reliability, security, documentation, portability and self-hosting are welcome.

Software Release Radar started as a heavily Codex-assisted, vibe-coded side project. I am not a software developer, so experienced contributors who can improve code structure, testing, security and maintainability are especially welcome.

AI-assisted contributions are welcome too. Please review generated code before submitting it and be able to explain what the change does and why it is safe.

Read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before participating in project spaces.

## Before opening an issue

- Search existing issues first.
- Use the bug report form for reproducible defects.
- Use the feature request form for proposed changes.
- Use a thumbs-up reaction to support an existing feature request instead of adding `+1` comments.
- Use Discussions for configuration questions and deployment help.
- Do not disclose security vulnerabilities in a public issue. Follow `SECURITY.md`.

## Development workflow

Maintainers and operators should also read [GitHub development and deployment workflow](docs/GITHUB-WORKFLOW.md).

1. Fork the repository.
2. Create a focused branch.
3. Read the relevant source, tests and `AGENTS.md` before changing behaviour.
4. Keep changes small enough to review.
5. Add or update tests when behaviour changes.
6. Run the Python test suite.
7. Validate Docker Compose for deployment changes.
8. Build and start a clean stack when runtime behaviour changes.
9. Update documentation when configuration or user-visible behaviour changes.
10. Open a pull request using the repository template.

## Python tests

Use Python 3.13.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

CI runs the complete test suite on every push to `main` and on pull requests.

## Docker validation

For the first local Docker setup:

```bash
bash scripts/setup.sh
```

After `.env` exists, rebuild the current working tree with:

```bash
docker compose config
docker compose up -d --build
docker compose ps
curl -fsS http://localhost:9120/healthz
```

A runtime change should leave:

- `software-release-radar` healthy;
- `software-release-radar-scheduler` running; and
- `software-release-radar-inventory-worker` running.

The GitHub CI workflow also performs a fresh Docker build and clean Compose smoke test.

## AI-assisted code

There is no requirement to avoid coding assistants. The project itself has been built with extensive help from OpenAI Codex.

For AI-assisted changes:

- read the generated code before submitting it;
- remove unnecessary complexity and generated filler;
- add or update tests for changed behaviour;
- check that comments and documentation describe the real behaviour;
- do not paste secrets, private infrastructure details or sensitive logs into prompts or commits; and
- keep the pull request small enough for another person to understand and review.

A contribution is judged on correctness, safety, clarity and maintainability, not on whether every line was typed by hand.

## Contribution rules

- Do not commit secrets, real credentials, private keys, production databases or deployment backups.
- Do not add real private hostnames, private DNS names, internal IP addresses or identifiable infrastructure screenshots.
- Documentation examples should use neutral names and documentation-only IP ranges.
- New outbound network integrations must be documented.
- Mutating operational commands should require explicit confirmation.
- Core release checks should remain deterministic. Optional AI behaviour must stay separable from core monitoring.
- A real `.env` file must remain local. Update `.env.example` when a new public deployment option is required.
- New background work must fail safely and remain observable through logs or persisted status.
- Database changes must be backward-compatible or include a documented migration and rollback plan.

## Pull request expectations

A pull request should explain:

- the problem being solved;
- the behaviour that changed;
- how the change was tested;
- any new configuration or network access; and
- any security, privacy or upgrade implications.

Do not combine unrelated refactors with a behavioural fix unless they are necessary for the same change.

## Licence of contributions

By submitting a contribution, you represent that you have the right to submit it and agree that the contribution may be distributed under GNU AGPL-3.0, the repository licence.
