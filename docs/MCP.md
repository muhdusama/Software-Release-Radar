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
- `MCP_AUTH_FAILURE_LIMIT`: 20, range 1 to 1000.

Authenticated message limits include discovery and are shared across processes.
Operation quotas apply to accepted dispatches, with per-key/global concurrency
and a single outstanding check or probe per tracker. Invalid attempts also have
a fixed global limit of 200 per ten-minute window; valid keys are not blocked
by the invalid-authentication bucket.
Browser and scheduler quotas are unchanged. Schema changes are additive and
idempotent; disabling the profile does not remove keys or other stored data.
The MCP uvicorn process also limits concurrent connections/tasks to 32,
including authenticated GET/SSE and subscription streams. Saturation returns
503 and can temporarily affect MCP liveness; it does not affect the separate
web service. The invalid-authentication limiter is SQLite-backed: it bounds
stored failures and response quotas, not incoming request/database write rate.

## Phase-1 tools and side effects

`read` provides cached `radar_status`, `trackers_list`, `tracker_get`,
`releases_list`, `history_list`, `upgrades_list` and `upgrade_get`. Current
administrators also get `inventory_list`, `inventory_summary` and `job_get`.
Lists use ascending ID keyset pagination, default 25 and maximum 100 items;
follow `next_after_id` until null. UTF-8 response limits can shorten a page.
Free text, including release notes, is untrusted data, never agent instructions.
Reads never contact upstream providers. `check_state` describes eligibility,
not a guarantee that a scheduler is running. Non-admin responses omit probe
destinations; cached errors are replaced with fixed safe summaries.

Current administrators with `operations:run` can use:

- `tracker_check(tracker_id, confirm=true)`: GitHub lookup, optional configured
  model analysis and standard release notifications; never probes or refreshes
  inventory. Disabled trackers remain explicitly checkable.
- `tracker_probe(tracker_id, confirm=true)`: existing browser-configured probe
  destinations or cached inventory only; never refreshes inventory. Returns
  live/cached source and cached inventory sync time when applicable.
- `inventory_sync()`: enqueue or reuse an inventory job. The existing worker
  contacts the configured provider later; the MCP call does not sync inline.

There are no data-write tools until separately reviewed Phase 2 is authorised.
Existing event uniqueness and recorded notification delivery suppress ordinary
retries, but the browser/scheduler can still race a check. Exactly-once external
effects and new auto-analysis/notification deduplication are not claimed.

## Durable operation ownership and offline recovery

Operation leases have **no automatic expiry**. The SDK worker owns its lease
until work and the transactional outcome audit finish, even after client
disconnect. If audit fails, ownership remains. Startup, elapsed time, key
revocation and account deletion never reclaim it. The former
`MCP_OPERATION_LEASE_SECONDS` setting is ignored and no longer configured.

A crashed worker or failed outcome audit can indefinitely block a tracker,
key or global capacity. A busy response therefore gives no promised retry
time. Read tracker release/check/probe state and audit dispatch/outcome records
before retrying an operation whose outcome is unknown.

**Only recover after stopping and verifying every MCP worker sharing the
database.** This includes workers on other containers/hosts. The utility cannot
prove shutdown: its flag is the operator assertion, not a safety check. Never
run it while an old worker can continue external work. Production recovery
requires separate, target-specific authorisation.

1. Stop all MCP instances using the actual deployment tooling. In a single
   Compose deployment, `docker compose --profile mcp stop mcp` stops that
   instance only; verify all relevant processes/containers have exited.
2. Privately inspect current tracker state and audit records. Recovery does not
   undo work, resend notifications or prove an exactly-once outcome.
3. From the application checkout, with the correct `RADAR_DB` and database
   access, run `python scripts/mcp_recover_leases.py --confirm-workers-stopped`.
   For Compose, a one-off `docker compose --profile mcp run --rm --no-deps mcp
   python scripts/mcp_recover_leases.py --confirm-workers-stopped` uses the
   service database without starting the MCP server. Without the flag the
   utility does not mutate anything. Audit and lease deletion are atomic;
   failure retains ownership. It changes no job, tracker, key or rate counter.
4. Restart MCP only after recovery; re-read tracker state before retrying.

Keep additive tables on rollback. Disabling the optional profile stops new
MCP calls; it is not permission to clear a still-running operation lease.
