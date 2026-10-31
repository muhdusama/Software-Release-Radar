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
Read is required; only administrators can grant `operations:run`,
`trackers:write` or `upgrades:write`. MCP cannot manage users, roles or keys, read
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

## Read tools and operation side effects

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

## Constrained data writes

Current administrators with `trackers:write` can use `tracker_create(tracker)`,
`tracker_update(tracker_id, changes)`, `tracker_set_enabled(tracker_id, enabled)`
and `tracker_delete(tracker_id, confirm=true)`. Allowed fields cover name,
repository on creation only, release/tag strategy, prereleases, enabled state,
homepage, notes, tags, refresh interval and manually recorded installed version.
Unknown fields are rejected. No probe destinations, credentials or arbitrary
settings can be configured. Saves never check, probe or sync implicitly.
Ordinary edits retain scheduling state; strategy/prerelease changes clear
release-check state and become due, retaining event history. Repository is
immutable after creation. Delete reports removed event and upgrade-decision
counts and requires explicit confirmation.

`upgrades:write` enables `upgrade_save_review(tracker_id, release_key,
expected_revision, review)`. First read `upgrade_get` and submit its exact
release key and integer revision. Review fields are decision status
(`review`, `update`, `wait`, `ignore`), priority, risk, maintenance date,
checklist, notes, rollback notes and change-record URL. A stale revision,
unknown historical release or already-deployed decision conflicts: read again,
reconcile and resubmit, never blindly retry. Each save increments revision.
Browser forms use the same atomic helper and revision binding. Marking deployed
and installed-version deployment assertions remain browser-only.

Writes share a 30-per-key, one-minute quota. Data changes and key-attributed
audit commit together or roll back together. No MCP tool deploys software.

## Existing operational limitations

Existing event uniqueness and recorded notification delivery suppress ordinary
retries, but the browser/scheduler can still race a check. Exactly-once external
effects and new auto-analysis/notification deduplication are not claimed.
Inventory jobs use the existing worker; stuck-running job recovery is unchanged.

## SDK client and verification

Use the official installed SDK with environment-held values, never a key in a
committed configuration or command argument:

```python
import asyncio
import os
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    async with httpx2.AsyncClient(trust_env=False, headers={
        "Authorization": "Bearer " + os.environ["RADAR_MCP_KEY"]
    }) as http:
        async with streamable_http_client(os.environ["RADAR_MCP_URL"], http_client=http) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                print(await client.call_tool("radar_status", {}))

asyncio.run(main())
```

The transport uses stateless HTTP and JSON POST responses. Authenticated
GET/SSE is SDK-native and shares the process connection cap. Inaccessible
tools are absent from discovery and behave like unknown names at dispatch.
API keys are revalidated on each request/message and mutation; last-used
metadata is updated at most once a minute, not an activity ledger.

Run `python scripts/mcp_acceptance.py --project srr01-4-acceptance` for isolated
local acceptance. It refuses an existing project, generates dummy secrets,
uses loopback ports and temporary SSH/configuration/backup paths, checks labels
before mutations, then removes only its own labelled project/volumes/images.
It never loads the deployment `.env`. Backup/restore and archived-baseline
rollback run only inside that disposable project.

`python scripts/mcp_deploy_verify.py --record-dir "$RADAR_VERIFY_DIR"` is
read-only and refuses missing protected evidence. The existing private record
directory must contain `baseline.json` mode 0600 with `approved_sha`,
`head_before`, `image_ids_before` (list of SHA256 image IDs),
`backup_integrity: "ok"`, `backup_mode: "0600"` and true booleans
`maintenance_authorised`, `git_workflow_verified`, `route_verified`, recorded
from real preflight, not inferred. Supply HTTPS `RADAR_PUBLIC_URL`,
`RADAR_MCP_URL`, `RADAR_MCP_KEY` and an owner-created already-revoked
`RADAR_MCP_REVOKED_KEY` through protected environment. Default expected tool
set is all 18 admin tools; `RADAR_MCP_EXPECTED_TOOLS` can explicitly provide the
exact JSON name list for a reduced-scope key. The verifier checks checkout,
service labels/health, live revision, SDK read/scopes and missing/revoked-key
401, creating only mode 0600 sanitised `verification.json` (refuses overwrite).
It never creates/revokes keys, deploys, pulls or performs operations/writes.

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
The restore helper refuses a locally running/paused/restarting MCP container;
operators must still verify workers outside that Compose project have stopped.
Baseline images predating revision binding do not increment review revisions.
If reviews were edited while rolled back, discard every cached review/form and
re-read before saving after rolling forward; old snapshots are not trustworthy.
