# Contributing

Contributions that improve reliability, security, documentation, portability and self-hosting are welcome.

## Before opening an issue

- Search existing issues first.
- Use the bug report form for reproducible defects.
- Use the feature request form for proposed changes.
- Do not disclose security vulnerabilities in a public issue. Follow `SECURITY.md`.

## Development workflow

1. Fork the repository.
2. Create a focused branch.
3. Keep changes small enough to review.
4. Add or update tests when behaviour changes.
5. Run the test suite.
6. Run `docker compose config`.
7. Build the container locally.
8. Open a pull request using the repository template.

Typical validation:

```bash
python -m unittest discover -s tests -v
docker compose config
docker build -t software-release-radar:dev .
```

## Contribution rules

- Do not commit secrets, real credentials, private keys, production databases or deployment backups.
- Do not add real private hostnames, private DNS names, internal IP addresses or identifiable infrastructure screenshots.
- Documentation examples should use neutral names and documentation-only IP ranges.
- New outbound network integrations must be documented.
- Mutating operational commands should require explicit confirmation.
- Core release checks should remain deterministic; optional AI behaviour must stay separable from core monitoring.

## Licence of contributions

By submitting a contribution, you represent that you have the right to submit it and agree that it may be distributed under the repository's current licence.

If the project later offers separate commercial licences, maintainers may require a contributor agreement before including contributions in those separately licensed distributions. No contributor agreement is required by this file alone.
