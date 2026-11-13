# Built-in authenticated MCP server

Status: revision 3. Proposed. Planning only. Awaiting owner approval. No implementation or deployment authorised.

Implementation plan: `docs/superpowers/plans/2026-10-31-built-in-mcp-implementation-plan.md`. That plan holds task order, tests, commands and the OpenChamber handoff. This document holds the design decisions and the evidence for them.

## Baseline

- Repository: `SRR-01-Software-Release-Radar-Community-Growth` (local path `/Users/muhdusama/Coding-Harness/SRR-01-Software-Release-Radar-Community-Growth`).
- Commit: `6624d4d2a2f03956a0cfc2397e064f461aaef6a1` on `main`, tracking `origin/main`, version 2.10.9.
- Working tree when revision 3 was written: clean apart from untracked `docs/superpowers/`, which holds only these planning documents.
- Proposed SDK: official `mcp` Python package 2.3.0 (released 2 October 2026), constrained to `mcp>=2.3.0,<2.4`.

Evidence labels used below: **Confirmed** means read in the current code or official SDK documentation. **Proposed** means a design change. **Assumption** means a fact that must be verified during implementation; each one has a compatibility check in the plan.

## Revision history

- Revision 1: initial design.
- Revision 2: corrected tracker-save side effects, repository-change history deletion, health check port and proxy rate limiting; removed settings:write; split into two phases.
- Revision 3: resolves eight review findings (disposition table below). Main changes: SDK 2.x native capabilities replace the explicit thread wrappers and low-level handlers in revision 2; HTTPS no longer trusts Host values; inventory reads are administrator-only; check and probe no longer refresh inventory or probe implicitly; operation leases are held for the life of the work; inventory enqueue and audit share one immediate transaction; upgrade reviews are bound to a release and revision; check-state wording is accurate.

## Intent and agreed boundaries

Let Hermes and other compatible MCP clients read and change Release Radar data through a built-in, authenticated MCP server. OpenChamber is the later implementation environment only; it is not an MCP client of this design.

Agents must not manage users, change roles, replace integration credentials, issue or revoke MCP keys, run arbitrary commands or SQL, change settings, send test notifications or deploy software. Never return passwords, password hashes, API keys, encrypted secrets, reset tokens, session material or private SSH key material.

API keys are the only MCP credential. Username and password sign-in remains the human path for creating and revoking keys in Profile. No OAuth service and no password exchange endpoint.

Not added: another database, Redis, a generic REST API, a custom MCP protocol implementation, an OAuth service or a general background-job platform. The existing SQLite database, inventory job queue and official SDK cover every requirement below.

## Confirmed facts about the existing code

- Flask under Gunicorn; scheduler and inventory worker are separate processes sharing SQLite (WAL, 30 second busy timeout) through `radar/db.py`.
- `transaction()` relies on Python's legacy implicit transactions: a `SELECT` does not start a transaction, and `BEGIN` (deferred) is issued only before the first write. Read-then-write sequences inside `transaction()` are therefore not atomic across processes.
- `_acquire_ai_lease` in `radar/security_controls.py` already uses explicit `BEGIN IMMEDIATE` for counters and leases.
- Sessions are bound to the password with `token_digest(password_hash)` (`radar/web.py` `load_user`). `token_digest` is SHA-256 (`radar/auth.py`).
- With `TRUST_PROXY_HEADERS=true` the web app applies `ProxyFix(x_for=1, x_proto=1, x_host=1)`, which trusts one forwarding hop from any peer.
- Connections that reach a container through a published Compose port arrive from the Docker bridge gateway, not from loopback. The Host header is chosen by the client.
- The inventory page and inventory sync routes (`/portainer`, `/portainer/sync`, `/portainer/sync-status`) are `@admin_required`. The dashboard, history and upgrades pages are `@login_required`; the dashboard shows machine name and install host and port to non-admin users.
- `check_tracker(tracker_id, baseline=False, run_probe=True, *, refresh_portainer=True)` performs a GitHub lookup unless the shared GitHub cooldown is active, then by default also probes, and an inventory-mode probe with `refresh_portainer=True` runs a full synchronous `sync_inventory()`.
- `_record_success` creates a release event only for a non-baseline change and, when `openai_auto_analyse` is `1`, calls `auto_analyse_event` inline (one model request, timeout at most 120 seconds).
- `probe_tracker(tracker_id, *, refresh_portainer=True)`: HTTP/TCP/SSH modes contact the configured destination (TCP 4 s, HTTP 8 s, SSH fixed command 15 s). Inventory mode with `refresh_portainer=False` reads cached inventory rows only.
- The browser single check dispatches notifications for a new event. The scheduler (`radar/scheduler.py`) checks enabled, due trackers each cycle and dispatches notifications only for events it created. An event not dispatched by its creator is never notified later.
- `events` has `UNIQUE (tracker_id, version)` and is written with `INSERT OR IGNORE`. `notification_deliveries` has `UNIQUE (event_id, user_id, channel)`.
- `is_due` treats NULL `last_checked_at` (and no retry time) as due. `github_retry_at` or the shared cooldown defers checks. The scheduler skips disabled trackers.
- The browser tracker form resets release state on strategy or prerelease changes but keeps `last_checked_at`, then runs an immediate check. A repository change also deletes the tracker's events.
- `enqueue_sync` performs `SELECT` for an active job then `INSERT`; under the transaction behaviour above, two concurrent callers can both insert. The worker has no recovery for a job left `running` by a crashed worker.
- `upgrade_decision` derives the target release at POST time from the URL or the current release, checks the deployed state from a row read before the write transaction, and updates without a version check. `updated_at` has one-second resolution. A save that races a mark-deployed can overwrite the deployed status.
- `audit()` opens its own transaction.
- The Dockerfile health check targets the web listener on port 8080.

## Confirmed SDK behaviour (mcp 2.3.0)

Sources: [PyPI mcp](https://pypi.org/project/mcp/), [What's new in v2](https://py.sdk.modelcontextprotocol.io/whats-new/), [Tools](https://py.sdk.modelcontextprotocol.io/servers/tools/), [Handling errors](https://py.sdk.modelcontextprotocol.io/servers/handling-errors/), [Cancellation](https://py.sdk.modelcontextprotocol.io/handlers/cancellation/), [Authorization](https://py.sdk.modelcontextprotocol.io/run/authorization/), [ASGI](https://py.sdk.modelcontextprotocol.io/run/asgi/), [Deploy and scale](https://py.sdk.modelcontextprotocol.io/run/deploy/), [Middleware](https://py.sdk.modelcontextprotocol.io/advanced/middleware/).

- High-level server is `MCPServer` (`from mcp.server import MCPServer`). Serving options (`stateless_http`, `json_response`, `transport_security`, paths) belong to `run()` and `streamable_http_app()`, not the constructor.
- Plain `def` tools run on a worker thread. No explicit thread wrapper is needed.
- A running `def` tool is never interrupted. With `json_response=True` (2026-07-28 protocol) or `stateless_http=True` (legacy protocol) the handler runs to the end whatever the client does.
- Tool arguments are validated from type hints before the function runs; validation failures return a tool error.
- An unexpected exception returns a generic "Error executing tool <name>" with no exception text. `ToolError` messages are forwarded to the client. `MCPError` is forwarded verbatim.
- `TokenVerifier.verify_token(token) -> AccessToken | None` with `AuthSettings`: the SDK verifies on every HTTP request, returns 401 itself, and exposes the result through `get_access_token()`. `token_verifier` and `auth` must be passed together.
- `TransportSecuritySettings(allowed_hosts, allowed_origins)`: invalid Host returns 421 and invalid Origin returns 403 before MCP processing; a missing Origin is accepted. Default allows only localhost hosts.
- `@mcp.custom_route` adds unauthenticated routes, suitable for liveness only.
- Middleware (`async (ctx, call_next)`, `ctx.method`, `ctx.params`) wraps every message and can answer or raise instead of calling the next handler. It is marked provisional and may change in a 2.x minor release, which is why the version is constrained to 2.3.x.
- Proxy headers are handled by uvicorn (`proxy_headers`, `forwarded_allow_ips`), which uses them only from listed peers.
- The SDK provides no request body size limit.
- Multiple uvicorn workers need shared request-state keys; a single worker avoids that.

Assumptions to verify against the installed 2.3.x package (plan task P1.0): which `AuthSettings` fields are mandatory and what protected-resource metadata it publishes; whether unknown tool arguments are rejected; whether `get_access_token()` is readable inside middleware; whether transport security applies to custom routes; whether uvicorn accepts CIDR values in `forwarded_allow_ips`; and that the resolver accepts the SDK alongside the existing pins (notably `cryptography<51` against `pyjwt[crypto]`). Each has a stated fallback in the plan.

## Selected architecture

- Optional Compose service `mcp` (profile `mcp`), same image and SQLite volume, started with `python -m radar.mcp_server`. That module calls `init_db()`, builds the `MCPServer`, and runs uvicorn with one worker on container port 8081.
- Serving options: `stateless_http=True`, `json_response=True`, endpoint `/mcp`. Both protocol generations then run without server-held sessions, and handlers always run to completion.
- Native SDK pieces: `TokenVerifier` and `AuthSettings` for bearer keys; `TransportSecuritySettings` for Host and Origin; `custom_route("/healthz")` for liveness; type-hint validation; exception masking; middleware for per-caller discovery and call filtering; uvicorn proxy-header handling.
- New code only where the SDK has no capability: one small ASGI wrapper for request body limit, HTTPS enforcement and invalid-authentication throttling; key storage and verification; leases and counters; tool functions over existing helpers.
- The existing Flask and Gunicorn entry point is unchanged. Existing installations start exactly as before without the profile.

## Finding 1: HTTPS and proxy trust

Decision (proposed):

- The MCP service does not use `TRUST_PROXY_HEADERS` or `ProxyFix`. It passes `RADAR_MCP_FORWARDED_ALLOW_IPS` to uvicorn. When the variable is empty, proxy headers are disabled entirely. Uvicorn's default of trusting 127.0.0.1 is never relied on.
- After uvicorn processing, the ASGI wrapper requires `scope["scheme"] == "https"` for every route except `/healthz`. The only exception is an explicit `RADAR_MCP_ALLOW_HTTP=true`. Host, Origin and client address are never used to infer that a connection is local or secure.
- Allowed Host values come from `RADAR_MCP_ALLOWED_HOSTS` and are required at startup; the service refuses to start without them. `RADAR_MCP_ALLOWED_ORIGINS` defaults to empty, so any supplied Origin is rejected and CORS stays disabled.

Supported arrangements:

1. Local development: host port bound to 127.0.0.1, `RADAR_MCP_ALLOW_HTTP=true`, allowed hosts `localhost:<port>` and `127.0.0.1:<port>`, no forwarded-header trust. Clients run on the same host. The startup log states that plain HTTP is enabled.
2. Published through a reverse proxy: the proxy terminates TLS and connects either to the loopback-published port (the peer the container sees is the Docker bridge gateway) or over a private Docker network (the peer is the proxy container). `RADAR_MCP_FORWARDED_ALLOW_IPS` lists exactly that peer address or network. The proxy overwrites `X-Forwarded-For` and `X-Forwarded-Proto` rather than appending client-supplied values, and forwards the public Host. The backend port is never published on a public interface. Allowed hosts list the public name.

Any other arrangement is unsupported in the first version.

## Finding 2: inventory permissions

Decision (proposed): `inventory_list`, `inventory_summary` and `job_get` require read scope and current administrator ownership, matching the `@admin_required` browser inventory routes. No existing policy justifies wider access. The same check applies in tools/list filtering and at call time. A non-admin key does not see these tools, and calling one directly returns the same error as an unknown tool.

## Finding 3: SDK assumptions

Decision (proposed): use mcp 2.3.x native behaviour as listed above. Revision 2 instructions for explicit `anyio.to_thread`, low-level `Server` handlers and overridden list methods are withdrawn. Discovery and call filtering use the documented middleware. Because middleware is provisional, the version is constrained to `<2.4`, and a test fails if filtering stops working after an upgrade.

## Finding 4: operational side effects

Decision (proposed). Browser and scheduler behaviour is not changed.

- `tracker_check` calls `check_tracker(tracker_id, run_probe=False)`. It may make one GitHub release lookup (none while a shared cooldown is active, in which case it reports deferred), update release state, and create a release event for a non-baseline change. If an event is created, the existing auto-analysis setting may make one model request inline. The tool then calls `dispatch_release_notifications([event_id])`, matching the browser check, so the new release is notified. It never probes and never synchronises inventory. Disabled trackers can be checked, matching the browser.
- `tracker_probe` calls `probe_tracker(tracker_id, refresh_portainer=False)` after the same configuration precondition as the browser route. HTTP, TCP and SSH modes make one live contact with the stored destination using the existing fixed commands and validation. Inventory mode reads cached inventory state only and reports it as cached, with the provider's last sync time. It never runs `sync_inventory()`.
- `inventory_sync` only enqueues a job for the existing inventory worker and returns the job ID. It never synchronises inline.
- Cached reads (`inventory_list`, `inventory_summary`, tracker probe fields) never contact anything.
- New rate limits, concurrency caps and leases apply only to MCP calls. Browser and scheduler work is neither counted nor blocked. The scheduler may still check a tracker at the same time as an MCP call, as the browser already can.

## Finding 5: timeouts and execution ownership

Decision (proposed):

- Before dispatch: authentication, scope, rate counters and lease acquisition happen in one `BEGIN IMMEDIATE` transaction. Any failure returns an error and nothing runs.
- Running: the tool body runs on the SDK worker thread and holds an `mcp_operation_leases` row (one per tracker for check and probe; global and per-key caps). The lease is released in a `finally` block inside the same thread after the operation returns, never when the response ends.
- Bounding: work is bounded by existing per-call outbound timeouts, which add up to a few minutes in the worst case (GitHub 20 s per request, model at most 120 s, SMTP and Pushover 15 s per send, probes at most 19 s). No server-side timeout wraps the synchronous work, because that would return while the thread kept running.
- Client timeout or disconnect: the server keeps running the operation to completion and records the outcome in audit and tracker state. The result is discarded. No response is promised after disconnection.
- Process failure: an in-flight operation may have partly happened. The audit trail shows a dispatch record with no outcome record. The lease expires after a fixed period (default 300 s, longer than the worst-case bound) so the tracker is not locked forever.
- Retry guidance (in tool descriptions): after an unknown outcome, read `tracker_get` (`last_checked_at`, `last_probe_at`, release state) before retrying. A retry while the first call still runs returns "operation already running" with a retry time. Repeating a check does not create a duplicate event (unique constraint) and does not resend notifications already recorded as sent or skipped. Probes are read-only against the target. Repeated `inventory_sync` reuses the active job. Exactly-once external effects are not claimed.

## Finding 6: transactional auditing and inventory enqueue

Decision (proposed; narrow shared-helper changes permitted in Phase 1):

- `transaction(immediate=False)` gains an option that issues `BEGIN IMMEDIATE`, matching `_acquire_ai_lease`.
- `audit(..., conn=None)` writes on the supplied connection when given; otherwise it behaves as today.
- `enqueue_sync(requested_by=None, *, conn=None)` runs inside the caller's transaction when given; otherwise it opens its own immediate transaction. The MCP tool opens one immediate transaction, enqueues, and audits on the same connection. The browser route keeps its call and gains the deduplication fix.
- Concurrent deduplication is verified by a multi-process test, not assumed.
- Data writes (Phase 2) audit on the same connection inside their immediate transaction. Denied calls, failed calls and external operations audit in their own transactions; check and probe write a dispatch record and an outcome record, which are explicitly not atomic with the external effect.

## Finding 7: upgrade-review integrity

Decision (proposed):

- Additive column `upgrade_decisions.revision INTEGER NOT NULL DEFAULT 0`.
- One shared helper in `radar/upgrade_workflow.py` performs the save inside `BEGIN IMMEDIATE`. It re-reads the tracker and decision, and requires the submitted `release_key` to equal the current release key, or to name a historical release that already has a decision. It rejects a deployed record, rejects a stale `expected_revision`, writes with `WHERE id = ? AND revision = ? AND decision_status <> 'deployed'`, increments `revision`, and audits on the same connection. A new row starts at revision 1, and a unique-constraint failure is a conflict.
- The browser route and form use the same helper. The form gains hidden `release_key` and `revision` fields. A stale or moved-release submission is refused with a warning instead of silently overwriting. Mark-deployed stays browser-only and goes through the same helper.
- MCP `upgrade_get` returns `release_key` and `revision`. `upgrade_save_review` requires both.

## Finding 8: contract details

Decision (proposed):

- Tracker responses include `check_state`, computed from existing scheduling functions:
  - `disabled`: the scheduler does not check it.
  - `deferred`: until `github_retry_at` or the shared cooldown ends, with that time.
  - `due`: eligible on the next scheduler cycle, if the scheduler service is running.
  - `scheduled`: with `next_due_at`.
- A created tracker has no `last_checked_at`, so it is `due` when enabled. Ordinary edits (name, notes, tags, homepage, refresh interval, manual version, enabled flag) leave scheduling timestamps unchanged. A strategy or prerelease change through MCP resets release state, as the browser does, and also clears `last_checked_at` so the tracker becomes due. This clearing is MCP-only because the browser checks immediately.
- `job_get` is an administrator-only read.
- Phase 1 keys can only hold `read` and `operations:run`. Phase 2 scopes are not offered, not storable and ignored at verification until Phase 2 is approved and shipped.
- Bounded safe projections, planted secret canaries and sanitised errors remain acceptance requirements.

## Disposition table

| # | Finding | Evidence | Chosen resolution | Acceptance test | Phase |
|---|---|---|---|---|---|
| 1 | HTTPS and proxy trust | ProxyFix trusts any peer; published ports arrive from bridge gateway; Host is client-controlled; SDK and uvicorn docs | uvicorn `forwarded_allow_ips` from explicit config, empty disables; wrapper requires https scheme unless `RADAR_MCP_ALLOW_HTTP=true`; Host never establishes locality; required allowed hosts | Plain-HTTP request with `Host: localhost` rejected; forwarded proto from an unlisted peer ignored; listed peer accepted; startup fails without allowed hosts | 1 |
| 2 | Inventory permissions | `/portainer*` routes are `@admin_required` | Read scope plus admin for inventory and job tools, in discovery and calls | Non-admin key: tools absent from tools/list, direct call gets unknown-tool error | 1 |
| 3 | SDK assumptions | mcp 2.3.0 docs: threaded `def` tools, TokenVerifier, TransportSecuritySettings, middleware | Native features; drop thread wrappers and low-level overrides; constrain `<2.4`; compatibility checks P1.0 | SDK client over real HTTP; filtering regression test; P1.0 check results recorded | 1 |
| 4 | Operational side effects | `check_tracker` and `probe_tracker` default flags probe and run full inventory sync; auto-analysis inside `_record_success` | `run_probe=False`; `refresh_portainer=False`; enqueue-only sync; notifications as browser; MCP-only limits | Mocks prove check never probes or syncs; probe never syncs; analysis called only when enabled and event created; browser and scheduler tests unchanged | 1 |
| 5 | Timeouts and execution ownership | SDK never interrupts threads; handlers run to completion in stateless/json mode | Lease held by the worker thread until the work ends; expiry for crashes; no server timeout wrapper; retry guidance | Lease still held after a simulated client timeout until the operation returns; concurrent same-tracker call refused; expired lease reclaimed | 1 |
| 6 | Audit and enqueue | Deferred implicit transactions; `audit()` own transaction; `enqueue_sync` SELECT then INSERT | `transaction(immediate=True)`, `audit(conn=)`, `enqueue_sync(conn=)` | Multi-process enqueue creates one job; audit row rolled back with a failed enqueue | 1 |
| 7 | Upgrade-review integrity | Release chosen at POST time; deployed check outside transaction; no version | `revision` column; immediate-transaction helper shared by browser and MCP; release binding; stale conflict | Moved release refused; stale revision refused; save racing mark-deployed cannot change a deployed row; browser form round trip | 2 |
| 8 | Contract details | `is_due`, scheduler skips disabled, form keeps `last_checked_at` | `check_state`; MCP source change clears `last_checked_at`; admin-only `job_get`; Phase 1 scope allowlist | `check_state` cases; Phase 2 scope cannot be created or used in Phase 1; canary and error tests | 1 and 2 |

## Authentication and authorisation

- Bearer keys only, in the `Authorization` header. No cookies, query strings or tool arguments.
- Key format `srr_<key_id>_<secret>`: random identifier for lookup, secret of at least 256 bits from `secrets`. The database stores `token_digest(secret)`, compared with `hmac.compare_digest`, plus the owner's `token_digest(password_hash)` at creation time.
- Profile key management (CSRF protected): create with current password, list metadata, revoke. The secret is rendered once in the POST response with `Cache-Control: no-store`. It is never put in a flash message, because flash data lives in the signed session cookie.
- Expiry defaults to 90 days, at most 365 days. Last-used time is updated at most once a minute.
- Every request re-reads the user and key: active user, current role, expiry, revocation and password binding. Effective scopes are the stored scopes intersected with the phase allowlist, minus mutation scopes if the owner is no longer an administrator.
- HTTP 401 comes from the SDK for missing or invalid keys. Permission failures are protocol-level: hidden tools are filtered from tools/list, and calling one returns the same unknown-tool error as a non-existent tool. Argument and execution errors are `ToolError` messages written by Release Radar, never exception text.

## Tool surface

Full schemas, limits and the scope, role and side-effect matrix are in the implementation plan.

- Phase 1, read: `radar_status`, `trackers_list`, `tracker_get`, `releases_list`, `history_list`, `upgrades_list`, `upgrade_get`; admin-only `inventory_list`, `inventory_summary`, `job_get`. Probe destination fields only for admin-owned keys. This is deliberately stricter than the browser dashboard.
- Phase 1, operations:run (admin): `tracker_check`, `tracker_probe`, `inventory_sync`.
- Phase 2, trackers:write (admin): `tracker_create`, `tracker_update`, `tracker_set_enabled`, `tracker_delete`. The repository cannot be changed after creation. Saves make no outbound request. Delete requires `confirm=true`.
- Phase 2, upgrades:write (admin): `upgrade_save_review`, bound to `release_key` and `revision`, never marks deployed.
- No settings tools, bulk operations, check-all or probe-all, imports, notification tests, user, key or credential tools.

`confirm=true` guards against accidental calls only. It is not a permission control.

## Known limitations

- A notification dispatch that races another dispatch for the same event (for example MCP and the scheduler) can send a duplicate message before either records delivery. This exists today between browser and scheduler and is not changed.
- An inventory job left `running` by a crashed worker blocks new sync jobs until handled manually. This is an existing worker limitation.
- OAuth-only MCP clients cannot connect. The protected-resource metadata published by `AuthSettings` (exact form verified in P1.0) does not lead to a working authorisation server.
- One uvicorn worker; the operation concurrency caps are small by design.
- Responses to timed-out or disconnected clients are lost; outcomes are visible only through later reads and the audit log.

## Rollout and rollback

No production deployment, credential provisioning, push, merge, release, DNS or proxy change, or live data migration is authorised. Schema changes are additive and idempotent. Disabling the `mcp` profile leaves the browser service unchanged. Keys are revoked in Profile. Back up with `scripts/backup.sh` before any separately authorised installation. Rollback keeps the additive tables and columns. The installation and rollback runbook is in the implementation plan and is gated separately.

## Workflow checklist

- [x] Inspect current implementation and deployment model.
- [x] Confirm agent administration exclusions with owner.
- [x] Revisions 1 and 2.
- [x] Revision 3: resolve review findings against code and SDK 2.3.0.
- [ ] Owner approves this design and the implementation plan.
- [ ] Separately authorised: Phase 1 implementation and isolated verification.
- [ ] Phase 1 independent review gate.
- [ ] Separately authorised: Phase 2 implementation and isolated verification.
- [ ] Phase 2 independent review gate.
- [ ] Separately authorised: commit, push and release.
- [ ] Separately authorised: production installation, key provisioning and proxy changes.

## 2026-10-31 owner-authorised rollout addendum

The owner said: "Approved. implement, deploy and record in youtrack" after this session presented its original written design. Read-back discovered that the shared file had been changed outside this session to revision 3, with material scope differences. The owner subsequently selected "Revision 3 (Recommended)" in the explicit authoritative-design question. Revision 3 now governs: no settings tools and separately gated phases. The revision text above is preserved unchanged; no external edits are discarded. Exact implementation-plan approval remains pending.

The current plan is `docs/superpowers/plans/2026-10-31-built-in-mcp.md`; the earlier plan filename mentioned above is historical and is not the current handoff. The approval-bound contract is `.dev/tasks/SRR01-4.json`, linked to https://youtrack.home.mmusama.com/issue/SRR01-4. Both implementation phases remain in scope. Exact-plan approval and execution-method selection are pending.

Production deployment is now requested, but the host, checkout and access route are not yet identified. Deployment requires confirmed target/configuration, verified backup and rollback, and the existing branch/PR/CI/review/merge workflow. Branch creation, commit, push, PR and merge require specific authority; public release/tag/image publication is not implied. No networking, DNS, proxy edits, new credential provisioning or destructive live restore is authorised. These blockers do not silently remove deployment from acceptance or grant missing authority.
