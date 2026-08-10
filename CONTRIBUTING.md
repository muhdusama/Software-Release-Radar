# 🤝 Contributing

Contributions that improve reliability, security, documentation, portability and self-hosting are welcome.

Software Release Radar started as a heavily Codex-assisted, vibe-coded side project. I am not a software developer, so experienced contributors who can improve code structure, testing, security and maintainability are especially welcome.

AI-assisted contributions are welcome too. Please review generated code before submitting it and be able to explain what the change does and why it is safe.

## Before opening an issue

- Search existing issues first.
- Use the bug report form for reproducible defects.
- Use the feature request form for proposed changes.
- Use a thumbs-up reaction to support an existing feature request instead of adding `+1` comments.
- Do not disclose security vulnerabilities in a public issue. Follow `SECURITY.md`.

## Development workflow

1. Fork the repository.
2. Create a focused branch.
3. Keep changes small enough to review.
4. Add or update tests when behaviour changes.
5. Run the test suite.
6. Run `docker compose config`.
7. Build the container locally.
8. Start the Compose stack when the change affects runtime behaviour.
9. Open a pull request using the repository template.

Typical validation after the public source and Dockerfile are staged:

```bash
python -m unittest discover -s tests -v
cp .env.example .env
docker compose config
docker compose up -d --build
docker compose ps
```

The repository is currently in publication staging. The Docker scaffold is present, but container validation cannot be completed until the sanitised application source and Dockerfile are imported.

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
- A real `.env` file must remain local. Update `.env.example` when a new public configuration option is required.

## Licence of contributions

By submitting a contribution, you represent that you have the right to submit it and agree that it may be distributed under the repository's current licence.

If the project later offers separate commercial licences, maintainers may require a contributor agreement before including contributions in those separately licensed distributions. No contributor agreement is required by this file alone.
