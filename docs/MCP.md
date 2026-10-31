# MCP connections

The optional `mcp` Compose profile runs the official Python MCP SDK in one
process on container port 8081. The browser, scheduler and inventory worker
do not depend on it. `/healthz` reports only `{"status":"ok"}`.

## Authentication

Sign in to the browser and open Profile to create a scoped API key. Creation
requires your current password and CSRF protection. Copy the secret once and
store it securely. Keys expire after 90 days by default (maximum 365), can be
revoked by their owner, and become invalid after a password change or account
deactivation. Current account permissions are checked again on each request.
Read is required; only administrators can grant `operations:run`. Phase 2
write scopes are not yet enabled. MCP cannot manage users, roles or keys, read
or replace credentials, change settings, or run deployments or arbitrary commands.

Supply keys only as `Authorization: Bearer <key>` over the MCP connection.
Passwords, browser cookies and query parameters are not credentials for MCP.
OAuth-only clients are not supported: metadata identifies the protected resource
but there is no OAuth login, password exchange or token issuance endpoint.

## Transport and deployment

The host port is always loopback-only: `127.0.0.1:9121`. Enabling the profile
does not configure a reverse proxy, certificates or DNS. The service refuses
to start without explicit `RADAR_MCP_ALLOWED_HOSTS` (comma-separated exact Host
values, including ports when used). `RADAR_MCP_ALLOWED_ORIGINS` defaults to
empty, rejecting any supplied Origin. No CORS is enabled. These checks cover
health and discovery routes as well as `/mcp`.

`RADAR_MCP_PUBLIC_URL` names the externally used URL ending in `/mcp`, with
an allowed host. If empty, it defaults to HTTPS on the first allowed host.
Except for liveness, every route requires HTTPS unless
`RADAR_MCP_ALLOW_HTTP=true` explicitly enables local development HTTP.

For local development, set allowed hosts to `localhost:9121,127.0.0.1:9121`,
public URL to `http://localhost:9121/mcp`, and allow HTTP to `true`. Then run
`docker compose --profile mcp up -d --build`. Do not use this HTTP exception
for a published connection.

For an existing TLS reverse proxy, leave allow HTTP false and set
`RADAR_MCP_FORWARDED_ALLOW_IPS` to its exact backend peer IP or CIDR. The proxy
must overwrite client-supplied forwarded headers and preserve the public Host.
Empty peer configuration disables proxy headers entirely. Wildcard trust is
rejected. `TRUST_PROXY_HEADERS` has no effect on the MCP process. Do not infer
trust from `Host: localhost` or a forwarded client IP. Keep the backend private.

Request bodies are capped at 128 KiB of actual bytes, including streamed
bodies. Invalid or negative content lengths are rejected before parsing.
Invalid credentials allow 20 attempts per source and 200 globally per rolling
10 minutes; subsequent failures return 429. Valid keys still authenticate in
that window. SQLite stores HMAC source buckets, not source addresses or tokens.

## MCP-only limits

Operator numeric settings use the existing bounded integer parser: invalid
integers use the default and out-of-range integers are clamped. Defaults and
inclusive ranges:

- `MCP_KEY_MINUTE_LIMIT`: 120, range 1 to 10000.
- `MCP_OPERATION_HOURLY_LIMIT`: 20, range 1 to 1000.
- `MCP_OPERATION_KEY_CONCURRENCY`: 1, range 1 to 4.
- `MCP_OPERATION_GLOBAL_CONCURRENCY`: 2, range 1 to 16.
- `MCP_OPERATION_LEASE_SECONDS`: 300, range 300 to 3600.
- `MCP_AUTH_FAILURE_LIMIT`: 20, range 1 to 1000.

Only the invalid-authentication limit is active at this implementation stage;
message and operation enforcement arrives with tool registration. Operational
lease expiry must exceed the full work duration before operations can ship.
Browser and scheduler quotas are unchanged. Schema changes are additive and
idempotent; disabling the profile does not remove keys or other stored data.
