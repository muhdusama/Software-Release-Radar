# Security policy

## Supported versions

Security fixes are targeted at the latest published release. Older releases may not receive backported fixes.

## Reporting a vulnerability

Do **not** open a public GitHub issue for a security vulnerability.

Use GitHub's private vulnerability reporting feature on the repository's Security page. Include:

- affected version;
- affected component;
- reproduction steps;
- expected and actual behaviour;
- potential impact; and
- any proposed mitigation.

If private vulnerability reporting is temporarily unavailable, open a non-sensitive issue asking for a private security contact without publishing exploit details.

## Deployment controls

Review [Security hardening](docs/SECURITY-HARDENING.md) and [Security controls](docs/SECURITY-CONTROLS.md) before exposing a deployment beyond a trusted local network.

The application blocks credential-bearing cleartext integrations by default. Do not enable `ALLOW_INSECURE_INTEGRATIONS` unless the network exception is understood and accepted.

## Sensitive data

Security reports must not include real production secrets unless absolutely necessary. Redact passwords, API keys and tokens, SSH keys, session cookies, private hostnames, internal IP addresses, database contents and personally identifiable information.

## Disclosure

Please allow maintainers a reasonable opportunity to reproduce, fix and publish a security update before public disclosure.
