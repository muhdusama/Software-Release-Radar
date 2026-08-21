# Security controls

This document describes the application controls added after the 2026-08-12 Codex Security audit.

## Password reset

Password-reset email never derives its destination origin from the request `Host` header.

Before password-reset email can be sent:

1. configure **Settings → General → Application base URL**;
2. use the exact origin users normally visit;
3. use HTTPS unless the application is available only through a loopback address; and
4. verify SMTP delivery through the Settings page.

The application base URL must contain only a scheme, hostname and optional port. Paths, query strings, fragments and embedded credentials are rejected.

Reset email is queued outside the browser request. Existing and unknown identities receive the same public response, reset requests remain rate limited, and the response has a small minimum duration to reduce timing differences.

## Assistant usage controls

Authenticated Assistant requests use persistent SQLite controls shared by Gunicorn workers.

Default limits:

| Control | Default |
|---|---:|
| Requests per user per 10 minutes | 10 |
| Requests per user per day | 50 |
| Requests per source address per hour | 30 |
| Concurrent requests per user | 1 |
| Concurrent requests for the deployment | 4 |
| Question length | 4,000 characters |
| Provider timeout | 120 seconds |
| Maximum response tokens | 4,096 |

Recent analyses for the same user, tracker, installed version and upstream release are reused for 15 minutes. Conversation messages and analysis history are also retained within bounded per-tracker limits.

The deployment-level limits can be adjusted through the corresponding `AI_*` variables in `.env`. Avoid removing limits entirely. Higher limits increase provider cost and the amount of work an authenticated account can force the server to perform.

## Integration transport

Reusable credentials are not sent over remote plain HTTP by default.

This applies to:

- OpenAI-compatible `Authorization` headers;
- Portainer `X-API-Key` headers; and
- Dockhand bearer authorisation headers; and
- SMTP delivery without STARTTLS or implicit TLS.

Loopback HTTP endpoints remain available for same-host integrations. An unauthenticated loopback SMTP relay may also use the `none` mode.

A deployment can explicitly accept a trusted-network exception with:

```text
ALLOW_INSECURE_INTEGRATIONS=true
```

This setting weakens transport protection and should remain `false` unless the network risk is understood and accepted. Prefer HTTPS, a trusted private certificate authority, STARTTLS or implicit TLS instead.

Credential-bearing HTTP responses are read through size-limited wrappers. Assistant requests also enforce prompt, output and provider-response limits.

## HTTP regular-expression probes

User-defined version regular expressions run through a timeout-capable engine with:

- a maximum pattern length;
- a bounded response slice;
- a bounded result length; and
- a hard execution timeout.

An expression that exceeds the time limit fails the probe rather than blocking a web or scheduler worker indefinitely.

## GitHub Actions

Every third-party GitHub Action used by the repository is pinned to a full commit SHA. Dependabot continues to monitor GitHub Actions and can propose reviewed SHA updates.

The container publishing workflow retains only the permissions it requires:

- `contents: read`
- `packages: write`

## Verification

The repository test suite includes regression coverage for:

- trusted password-reset origins;
- removal of request-host fallback;
- Assistant request length, rate, concurrency and deduplication;
- credential transport policy;
- provider response limits;
- regular-expression timeouts; and
- immutable GitHub Action references.
