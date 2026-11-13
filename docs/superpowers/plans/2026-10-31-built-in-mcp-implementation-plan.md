# Built-in MCP server: implementation plan

Status: Proposed. Planning only. Awaiting owner approval. No implementation or deployment authorised.

Design authority: `docs/superpowers/specs/2026-10-31-built-in-mcp-design.md` (revision 3). Where this plan and the design disagree, stop and ask the owner. Do not choose one silently.

Approving this document does not authorise any stage below. Each stage in "Execution stages and approvals" needs its own explicit owner approval, given in the implementation environment.

## 1. Scope, exclusions and baseline

### Scope

- Phase 1: API key storage and Profile key management; an optional MCP service (Compose profile `mcp`); authentication, transport and abuse controls; Phase 1 read tools; operations:run tools (`tracker_check`, `tracker_probe`, `inventory_sync`); narrow shared-helper fixes for immediate transactions, audit on a supplied connection and inventory enqueue deduplication; documentation.
- Phase 2, after the Phase 1 review gate: trackers:write and upgrades:write tools; upgrade review release binding and revision checks shared with the browser; a shared tracker validation helper.

### Exclusions

Settings tools; user, role, key or credential tools; bulk operations; check-all and probe-all; inventory imports; notification tests; probe destination, SSH or binding edits; repository changes after creation; marking deployed through MCP; OAuth; multiple uvicorn workers; changes to browser or scheduler behaviour beyond the two fixes named in P1.3 and P2.2; production installation; release actions.

### Baseline

- Repository: `SRR-01-Software-Release-Radar-Community-Growth`. The owner's request named `/coding-harness/...`; the checkout actually used is `/Users/muhdusama/Coding-Harness/SRR-01-Software-Release-Radar-Community-Growth`.
- Commit `6624d4d2a2f03956a0cfc2397e064f461aaef6a1` on `main`, version 2.10.9. Untracked `docs/superpowers/` holds only the design and this plan.
- Python 3.13 (Dockerfile `python:3.13-slim`). Runtime requirements: Flask, Werkzeug, Gunicorn, cryptography (`<51`), regex.
- 160 `def test_` functions across `tests/` by static count. Record the real pass count in P1.0.

### Prerequisites

- Owner approval of stage A (section 2) for the phase being implemented.
- Network access to PyPI for the SDK; Docker with Compose v2 for container checks.
- No live database, credentials, private hostnames or production services. All tests use temporary databases and mocks (section 9).

## 2. Execution stages and approvals

The agent never runs more than one stage per approval, and never moves to the next stage on its own.

| Stage | Contents | Approval needed before starting |
|---|---|---|
| A1 | Phase 1 implementation and isolated verification on a local branch | Owner approves this plan and stage A1 |
| Gate 1 | Independent security and correctness review of Phase 1; fix material findings; rerun checks | Automatic after A1, but Phase 2 cannot start until the owner accepts the review result |
| A2 | Phase 2 implementation and isolated verification | Owner accepts Gate 1 and approves stage A2 |
| Gate 2 | Independent review of Phase 2 | Owner accepts the review result |
| B | Version bump, changelog finalisation, commit, push, pull request, merge, image publication | Separate owner approval for each action (commit, push, PR, merge, publish) |
| C | Production backup, installation, key provisioning, proxy configuration, client connection | Separate owner approval; the owner performs key creation and proxy changes themselves |

Stage A work happens on a local feature branch. It does not commit unless the owner asks, and never pushes.

## 3. Configuration reference

New environment variables apply only to the `mcp` service. None are added to the shared `x-radar-environment` anchor, so existing services see no change. Do not use `${VAR:?}` in Compose for these variables; required values are enforced at service startup so `docker compose config` without the profile keeps working.

| Variable | Default | Meaning |
|---|---|---|
| `RADAR_MCP_BIND_ADDRESS` | `127.0.0.1` | Host interface for the published port (Compose `ports`) |
| `RADAR_MCP_PORT` | `9121` | Host port mapped to container port 8081 |
| `RADAR_MCP_ALLOWED_HOSTS` | none, required | Comma-separated Host values for `TransportSecuritySettings`; include `name` and `name:*` forms as needed |
| `RADAR_MCP_ALLOWED_ORIGINS` | empty | Comma-separated Origins; empty means any supplied Origin is rejected |
| `RADAR_MCP_FORWARDED_ALLOW_IPS` | empty | Proxy peer addresses or networks for uvicorn; empty disables proxy headers |
| `RADAR_MCP_ALLOW_HTTP` | `false` | `true` permits plain HTTP for local development only |
| `RADAR_MCP_PUBLIC_URL` | empty | Only if P1.0 shows `AuthSettings` requires a resource URL; the public `https://.../mcp` address |
| `MCP_KEY_MINUTE_LIMIT` | `120` | Accepted requests per key per minute |
| `MCP_OPERATION_HOURLY_LIMIT` | `20` | operations:run calls per key per hour |
| `MCP_OPERATION_KEY_CONCURRENCY` | `1` | Concurrent check or probe operations per key |
| `MCP_OPERATION_GLOBAL_CONCURRENCY` | `2` | Concurrent check or probe operations in total |
| `MCP_OPERATION_LEASE_SECONDS` | `300` | Lease expiry used only for crash recovery |
| `MCP_AUTH_FAILURE_LIMIT` | `20` | Invalid-authentication responses per client address per 10 minutes before throttling |

Range-check the numeric values the way `_int_env` does in `radar/security_controls.py`. Reuse that function rather than copying it.

## 4. Schema changes

All changes go in `init_db()` in `radar/db.py`: additive, idempotent, `CREATE TABLE IF NOT EXISTS` and `_add_column`.

Phase 1:

- `api_keys`: `id INTEGER PRIMARY KEY`, `key_id TEXT NOT NULL UNIQUE`, `user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE`, `name TEXT NOT NULL`, `secret_digest TEXT NOT NULL`, `scopes TEXT NOT NULL`, `password_stamp TEXT NOT NULL`, `created_at TEXT NOT NULL`, `expires_at TEXT NOT NULL`, `revoked_at TEXT`, `last_used_at TEXT`. Index on `user_id`. Keys are revoked, never deleted.
- `mcp_rate_counters`: same shape as `ai_security_counters` (`key TEXT PRIMARY KEY`, `requests`, `expires_at`, `updated_at`) with an expiry index. It is separate so MCP never touches Assistant limits.
- `mcp_operation_leases`: `id TEXT PRIMARY KEY`, `api_key_id INTEGER NOT NULL`, `user_id INTEGER NOT NULL`, `tool TEXT NOT NULL`, `tracker_id INTEGER`, `expires_at TEXT NOT NULL`, `created_at TEXT NOT NULL`, plus `UNIQUE (tool, tracker_id)` for check and probe. Index on `expires_at`.
- `audit_log.api_key_id INTEGER` (nullable, no foreign key, so audit survives any key change).

Phase 2:

- `upgrade_decisions.revision INTEGER NOT NULL DEFAULT 0`.

Rollback note: version 2.10.9 code ignores these additions, because its `init_db()` and queries name columns explicitly. Prove this in P1.10.

## 5. Tool contract

General rules for every tool:

- Plain `def` functions (the SDK threads them), typed parameters with bounds, `ToolAnnotations` set accurately, and descriptions that label upstream text and notes as untrusted data.
- Lists: `limit` 1 to 100 (default 25), keyset pagination with `after_id`, and `next_after_id` in the response.
- Text caps: errors 500 characters, notes 4,000, release bodies 4,000 in lists and 8,000 in `tracker_get`, each with a `truncated` flag.
- Errors: `ToolError` with fixed Release Radar messages. Never include exception text, SQL, paths, tokens or provider responses beyond the existing stored and capped `last_error` and `last_probe_error` fields.
- Projections are built from explicit column lists. No `dict(row)` and no `SELECT *` passthrough.

Probe destination fields, returned only to admin-owned keys: `machine_name`, `install_host`, `install_port`, `install_scheme`, `health_path`, `probe_mode`, `version_probe_path`, `version_json_path`, `version_regex`, `ssh_user`, `ssh_port`, `ssh_key_name`, `docker_container`, `portainer_service_id`, `last_probe_error`.

### Scope, role and side-effect matrix

| Tool | Scope | Admin owner | Phase | Annotations | Side effects |
|---|---|---|---|---|---|
| `radar_status` | read | no | 1 | read-only | none |
| `trackers_list` | read | no (admin sees probe fields) | 1 | read-only | none |
| `tracker_get` | read | no (admin sees probe fields) | 1 | read-only | none |
| `releases_list` | read | no | 1 | read-only | none |
| `history_list` | read | no | 1 | read-only | none |
| `upgrades_list` | read | no | 1 | read-only | none |
| `upgrade_get` | read | no | 1 | read-only | none |
| `inventory_summary` | read | yes | 1 | read-only | none (cached rows) |
| `inventory_list` | read | yes | 1 | read-only | none (cached rows) |
| `job_get` | read | yes | 1 | read-only | none |
| `tracker_check` | operations:run | yes | 1 | open-world, not idempotent | GitHub lookup; release state write; possible event; possible model request when auto-analysis is enabled; notification dispatch for a new event; audit |
| `tracker_probe` | operations:run | yes | 1 | open-world, idempotent | One live contact for HTTP/TCP/SSH modes; cached read for inventory mode; probe columns write; audit |
| `inventory_sync` | operations:run | yes | 1 | idempotent | Queue row (or reuse); audit; worker performs the sync later |
| `tracker_create` | trackers:write | yes | 2 | not idempotent | Tracker insert; audit; no outbound request |
| `tracker_update` | trackers:write | yes | 2 | idempotent | Tracker update; possible release state reset; audit; no outbound request |
| `tracker_set_enabled` | trackers:write | yes | 2 | idempotent | Tracker update; audit |
| `tracker_delete` | trackers:write | yes | 2 | destructive | Deletes the tracker, its events and decisions (cascade); audit |
| `upgrade_save_review` | upgrades:write | yes | 2 | not idempotent | Decision insert or update with revision; audit |

### Schemas

Phase 1:

- `radar_status()` returns `name`, `version`, `commit`, `github_cooldown_until`, `server_time`.
- `trackers_list(limit=25, after_id=None, enabled: bool|None=None, tag: str|None (max 64), query: str|None (max 120))` returns `items[TrackerSummary]` and `next_after_id`.
  - `TrackerSummary`: `id`, `name`, `repository`, `strategy`, `include_prereleases`, `enabled`, `tags[]`, `homepage_url`, `refresh_hours`, `current_version`, `current_release_name`, `current_published_at`, `installed_version`, `detected_installed_version`, `last_checked_at`, `last_status`, `last_error`, `last_probe_at`, `last_probe_status`, `last_probe_latency_ms`, `check_state`, `next_due_at`, `deferred_until`, plus `probe` (admin only).
- `tracker_get(tracker_id: int)` returns `TrackerSummary` plus `notes`, `current_release_url`, `current_release_body`.
- `releases_list(tracker_id: int, limit, after_id)` returns events: `id`, `version`, `release_name`, `release_url`, `published_at`, `detected_at`, `previous_version`, `notified`, `release_body`.
- `history_list(limit, after_id, tracker_id: int|None, since: date|None)` returns events with `tracker_id` and `tracker_name`, without bodies.
- `upgrades_list(limit, after_id, decision_status: Literal[...]|None)` returns `id`, `tracker_id`, `tracker_name`, `release_key`, `release_name`, `decision_status`, `priority`, `risk`, `maintenance_date`, `updated_at`, `revision` (Phase 2 column; return 0 in Phase 1).
- `upgrade_get(tracker_id: int, release_key: str|None (max 200))` returns the decision for the current release, or for the given historical release where a decision exists, or defaults with `revision` 0. Fields: `release_key`, `historical`, `decision_status`, `priority`, `risk`, `maintenance_date`, `checklist[{text, done}]`, `decision_notes`, `rollback_notes`, `change_record_url`, `installed_version_at_decision`, `deployed_version`, `deployed_at`, `revision`.
- `inventory_summary()` returns provider label, last sync time and status, a capped sync error, and counts of environments, services, linked and offline.
- `inventory_list(limit, after_id, linked: bool|None)` returns `id`, `provider`, `environment_name`, `container_name`, `image`, `state`, `present`, `detected_version`, `linked_tracker_id`, `updated_at`.
- `job_get(job_id: int)` returns `id`, `status`, `requested_at`, `started_at`, `completed_at`, `message`, progress counts, and `error` reduced to its first line and capped.
- `tracker_check(tracker_id: int, confirm: Literal[True])` returns `status` (`ok`, `error` or `deferred`), `changed`, `baseline`, `version`, `event_id`, `notifications{sent, failed, skipped}`, `deferred_until`, `error`.
- `tracker_probe(tracker_id: int, confirm: Literal[True])` returns `status`, `online`, `installed_version`, `latency_ms`, `source_kind` (`live` or `cached_inventory`), `inventory_synced_at` (cached only), `error`.
- `inventory_sync()` returns `job_id`, `reused`, `status`.

Phase 2:

- `tracker_create(name (1-120), repository, strategy: Literal["release","tag"]="release", include_prereleases=False, enabled=True, notes: str|None (max 4000), tags: list[str] (max 20), homepage_url: str|None, refresh_hours: int|None, installed_version: str|None (max 100))`.
- `tracker_update(tracker_id: int, ...same optional fields except repository)`: partial update of supplied fields only.
- `tracker_set_enabled(tracker_id: int, enabled: bool)`.
- `tracker_delete(tracker_id: int, confirm: Literal[True])` returns the deleted ID and the counts of events and decisions removed.
- `upgrade_save_review(tracker_id: int, release_key: str, expected_revision: int (>=0), decision_status: Literal["review","update","wait","ignore"], priority, risk, maintenance_date: date|None, decision_notes: str|None (max 10000), rollback_notes: str|None (max 10000), change_record_url: str|None, checklist: list[{text (1-300), done: bool}] (max 50))` returns the saved decision with its new `revision`.

Unknown arguments are rejected. If P1.0 shows the SDK ignores extra arguments, the authorisation middleware rejects any `tools/call` argument name absent from that tool's advertised input schema.

## 6. Phase 1 tasks

### P1.0 Preflight and SDK compatibility checks

1. Record `git status --short --branch`, `git rev-parse HEAD`, and the result of `python -m unittest discover -s tests -v` (pass count) before any change. If HEAD is no longer `6624d4d`, diff the files named in this plan against it and stop for owner direction if any named function changed.
2. Revalidate the dependency (section 11). Install it into a disposable virtual environment, never the system interpreter.
3. Check each design assumption against the installed package, record the result in the evidence notes, and apply the fallback where the check fails:

| Check | Pass condition | Fallback |
|---|---|---|
| `AuthSettings` mandatory fields and published metadata | Works with a Release Radar `TokenVerifier`; record any `/.well-known` route it adds | Set `issuer_url` and `resource_server_url` from `RADAR_MCP_PUBLIC_URL`; document the limitation for OAuth-only clients |
| Unknown tool arguments | Rejected before the function runs | Middleware rejects names absent from the advertised schema |
| `get_access_token()` inside middleware | Returns the verifier's token | Middleware re-reads the key from the `Authorization` header through the same verification function |
| Middleware can filter a `tools/list` result | Result returned from `call_next` can be reduced | Stop and ask the owner; do not override SDK methods |
| Transport security on custom routes | Record whether `/healthz` is subject to Host checks | Include `127.0.0.1:8081` in the health check's Host, or add it to allowed hosts |
| uvicorn `forwarded_allow_ips` accepts networks | A CIDR value is honoured | Document that exact addresses are required |
| Sync tool threading | A `def` tool runs off the event-loop thread | Stop and ask the owner |

### P1.1 Shared transaction and audit helpers (`radar/db.py`)

- `transaction(immediate: bool = False)`: when true, execute `BEGIN IMMEDIATE` straight after connecting. Existing callers are unchanged.
- `audit(..., conn=None, api_key_id=None)`: write on `conn` when supplied, otherwise open a transaction as today.
- Schema additions from section 4 (Phase 1 items).
- Tests: an immediate transaction blocks a second writer until commit; `audit(conn=...)` rolls back with the caller; old call signature unchanged.

### P1.2 Key storage and verification (new `radar/api_keys.py`)

- Constants: `PHASE_SCOPES = {"read", "operations:run"}` (Phase 2 extends it); `ADMIN_SCOPES = {"operations:run"}`.
- `create_key(user_row, name, scopes, expires_days)`: validate scopes against `PHASE_SCOPES`, require read, refuse admin scopes for non-admins, expiry 1 to 365 days. Generate `key_id` (`secrets.token_hex(8)`) and secret (`secrets.token_urlsafe(32)`). Store digests. Audit `api_key_created`. Return the full key once.
- `list_keys(user_id)`: metadata only. `revoke_key(user_id, key_row_id)`: own keys only; audit.
- `resolve_key(raw)`: parse the format, look up by `key_id`, compare digests with `hmac.compare_digest`, join the user, then require active user, not expired, not revoked, and matching password stamp. Compute effective scopes (stored ∩ `PHASE_SCOPES`, minus admin scopes for non-admins). Return a frozen principal (key row ID, user ID, role, scopes) or `None`. Update `last_used_at` at most once a minute.
- Tests: format and digest; each invalidation path (expired, revoked, disabled user, deleted user, password changed, demoted admin losing `operations:run`); a stored Phase 2 scope is ignored; timing-safe comparison used.

### P1.3 Inventory enqueue deduplication (`radar/portainer_jobs.py`)

- `enqueue_sync(requested_by=None, *, conn=None)`: with `conn`, run the select and insert on it (the caller holds an immediate transaction); without it, open `transaction(immediate=True)`. The browser route `portainer_sync_route` keeps its call unchanged and gains the fix.
- Tests: two processes (`multiprocessing`, same temporary database) enqueue at once and exactly one job is created, with the other told it was reused; an MCP-style caller's audit row and job row both roll back when the transaction fails.

### P1.4 Profile key management (`radar/web.py`, `radar/templates/profile.html`)

- `POST /profile/api-keys` (`@login_required`, `require_csrf`, current password re-verified, Phase 1 scope choices only; admin scope offered only to admins). On success render `profile.html` directly with the one-time key and `Cache-Control: no-store`. Never use `flash` for the key.
- `POST /profile/api-keys/<int:key_id>/revoke` (`@login_required`, `require_csrf`, own keys only, redirect with a flash that contains no secret).
- Profile lists name, `key_id` prefix, scopes, created, expires, last used and revoked state.
- Copy in Australian English, no contractions.
- Tests: CSRF required; wrong password refused; non-admin cannot request `operations:run`; secret appears once and not on reload; `no-store` header present; session cookie never contains the secret; revoke affects only own keys; existing profile update still works.

### P1.5 MCP service module (new `radar/mcp_server.py`)

- `build_server()` constructs `MCPServer` with the `TokenVerifier` (calls `resolve_key`; maps the principal into `AccessToken`: `client_id` = key row ID, `subject` = user ID, `scopes` = effective scopes, `expires_at`) and `AuthSettings` per P1.0.
- Middleware `authorise`: for `tools/list`, filter to tools the current principal may use (scope plus admin rule from section 5); for `tools/call`, refuse unknown or hidden tools with the same unknown-tool error, re-check scopes, apply per-key rate counters and the unknown-argument rule if needed, and audit denials (`mcp_denied`, tool name, no arguments).
- `build_app()` returns `mcp.streamable_http_app(stateless_http=True, json_response=True, transport_security=TransportSecuritySettings(allowed_hosts=..., allowed_origins=...))`, wrapped by a small ASGI wrapper:
  - Request body limit 128 KiB: reject a larger `Content-Length` with 413, and count streamed bytes.
  - HTTPS rule: `scope["scheme"] == "https"` unless `RADAR_MCP_ALLOW_HTTP=true`; `/healthz` exempt.
  - Invalid-authentication throttle: count 401 responses per `scope["client"]` address in `mcp_rate_counters`. While an address is over `MCP_AUTH_FAILURE_LIMIT`, call `resolve_key` on the presented header. Pass through when valid, otherwise return 429 with `Retry-After`. A valid key is never blocked.
  - Never log `Authorization` headers or bodies.
- `@mcp.custom_route("/healthz")` returns `{"status": "ok"}` only.
- `main()`: `init_db()`, validate configuration (allowed hosts required; numeric ranges), then `uvicorn.run(app, host="0.0.0.0", port=8081, workers=1, proxy_headers=bool(ips), forwarded_allow_ips=ips or None, server_header=False)`. Log a warning when `RADAR_MCP_ALLOW_HTTP=true`.
- Tests: section 10 items T1 to T6.

### P1.6 Read tools (`radar/mcp_server.py`)

- Implement the Phase 1 read schemas with explicit column lists and existing helpers: `release_key`, `load_checklist` (`radar/upgrade_workflow.py`); `split_tags`, `next_due_at`, `is_due` (`radar/tracker_utils.py`); `shared_rate_limit_until` (`radar/github.py`); `inventory_summary()` (`radar/portainer.py`, as used by `portainer_inventory`) plus a bounded service query for `inventory_list`.
- `check_state` computation: disabled → `disabled`; `github_retry_at` or shared cooldown in the future → `deferred` with time; `is_due` → `due`; otherwise `scheduled` with `next_due_at`.
- Tests: projections contain only allowed keys; admin and non-admin probe field difference; inventory and job tools hidden and refused for non-admins; limits and pagination; truncation flags; `check_state` cases; no outbound mocks called.

### P1.7 Operations tools (`radar/mcp_server.py`)

- Lease helper following `_acquire_ai_lease`: one `transaction(immediate=True)` prunes expired leases, enforces per-key and global concurrency and `UNIQUE (tool, tracker_id)`, increments `MCP_OPERATION_HOURLY_LIMIT` counters, and inserts the lease. Release happens in `finally` inside the tool function after the work returns.
- `tracker_check`: lease, audit `mcp_tracker_check_dispatched`, `check_tracker(tracker_id, run_probe=False)`, then if `event_id` call `dispatch_release_notifications([event_id])`, audit `mcp_tracker_check_completed` with the outcome, release the lease.
- `tracker_probe`: same browser precondition as `probe_one` (inventory mode or install host present, else `ToolError` without contact), lease, audit, `probe_tracker(tracker_id, refresh_portainer=False)`, audit outcome, release. Report `source_kind` and the provider's `<provider>_last_sync_at` for cached results.
- `inventory_sync`: `with transaction(immediate=True) as conn`, `enqueue_sync(principal.user_id, conn=conn)`, `audit(..., conn=conn, api_key_id=...)`.
- Tool descriptions state the side effects and retry guidance from design finding 5.
- Tests: section 10 items T7 to T11.

### P1.8 Compose service (`docker-compose.yml`)

- New service `mcp`: `profiles: ["mcp"]`; same `image` and `build` as the others; `environment` merges the anchor plus the section 3 variables; `command: ["python", "-m", "radar.mcp_server"]`; `ports: ["${RADAR_MCP_BIND_ADDRESS:-127.0.0.1}:${RADAR_MCP_PORT:-9121}:8081"]`; `volumes` as `scheduler` (data and read-only SSH, since probes may use SSH); `extra_hosts` as the others; `depends_on: radar: service_healthy`; `restart: unless-stopped`.
- `healthcheck` overrides the image check with a Python urllib request to `http://127.0.0.1:8081/healthz` (Host handling per P1.0).
- No change to `radar`, `scheduler` or `portainer-worker`, and no Dockerfile change apart from the dependency arriving through `requirements.txt`.

### P1.9 Dependency (`requirements.txt`)

- Add `mcp>=2.3.0,<2.4` (adjust per section 11 revalidation). Do not add the `cli` or `rich` extras.

### P1.10 Documentation and compatibility

- `docs/CONFIGURATION.md`: section 3 variables.
- `docs/DOCKER.md`: the profile, the two supported arrangements from design finding 1, reverse proxy requirements with placeholder names, and a Hermes or generic HTTP client example using an environment variable for the key.
- `docs/SECURITY-CONTROLS.md`: MCP controls and known limitations.
- `docs/ARCHITECTURE.md`: the optional process.
- `CHANGELOG.md`: an unreleased entry. Versioning is stage B.
- Rollback compatibility: start version 2.10.9 code (`git worktree` at `6624d4d` in a temporary directory) against a copy of a temporary database migrated by the new code, and confirm `init_db()` and the dashboard work.

### Phase 1 completion criteria

- All section 10 Phase 1 tests pass, plus the whole existing suite with no reduction from the P1.0 pass count.
- Section 12 commands produce the expected outcomes, or their unavailability is reported explicitly.
- P1.0 compatibility results and fallbacks recorded.
- A secret-canary run shows no canary in responses, protocol errors, audit rows or captured logs.
- No change to the browser or scheduler beyond the P1.3 deduplication fix, shown by a diff review of `radar/web.py` (only the P1.4 routes and template) and `radar/scheduler.py` (unchanged).

### Gate 1

An independent reviewer (a reviewer other than the implementing agent, chosen by the owner) checks authentication, scope filtering, proxy and HTTPS handling, leases, transactions, projections and error sanitisation against the design. Material findings are fixed and affected checks rerun. The owner accepts the result before stage A2 is requested.

## 7. Phase 2 tasks

### P2.1 Tracker validation helper (`radar/tracker_utils.py` or a new `radar/tracker_service.py` if import cycles require it)

- `validate_tracker_core(values: dict, *, existing=None) -> dict` for the allowlisted fields: name length, `normalise_repository`, strategy, prerelease, enabled, `normalise_tags`, homepage URL (move the `_safe_optional_url` logic out of `radar/web.py` and keep a thin delegating name there), `validate_refresh_hours`, installed version length.
- `reset_release_state(conn, tracker_id, *, clear_last_checked: bool)`: the existing reset SQL from `tracker_form`.
- `tracker_form` uses `validate_tracker_core` and `reset_release_state(clear_last_checked=False)`. Its probe-field handling, repository-change event deletion, write and immediate check remain as they are.
- Tests: existing browser tracker tests unchanged and passing; new tests for the helper's error messages matching the previous form messages.

### P2.2 Upgrade save helper (`radar/upgrade_workflow.py`, `radar/web.py`, `radar/templates/upgrade_decision.html`)

- Add the `revision` column (section 4).
- `validate_checklist(items)` shared by `checklist_from_form` and MCP.
- `save_upgrade_decision(*, tracker_id, release_key, expected_revision, fields, user_id, mark_deployed=False, api_key_id=None) -> (decision_id, revision)` inside `transaction(immediate=True)`:
  1. Re-read the tracker. Current key = `release_key(tracker)`.
  2. If `release_key != current`, require an existing decision for it, else conflict `release_changed`. Historical releases cannot be marked deployed.
  3. Existing row deployed → `DeployedRecordImmutable`.
  4. `expected_revision` differs from the row (or is not 0 for a missing row) → `StaleRevision` carrying the current revision.
  5. Update `... revision = revision + 1 WHERE id = ? AND revision = ? AND decision_status <> 'deployed'` and require `rowcount == 1`; or insert with revision 1 and map a unique-constraint failure to `StaleRevision`.
  6. Audit on the same connection.
- Browser: the form adds hidden `release_key` and `revision` inputs; `upgrade_decision` POST calls the helper and maps each conflict to a warning flash and redirect without saving.
- Tests: moved release refused (browser and MCP); stale revision refused; a save racing mark-deployed in two processes leaves the deployed row unchanged; a normal browser save and mark-deployed still work; historical notes save still works; deployed record still immutable.

### P2.3 Phase 2 tools (`radar/mcp_server.py`, `radar/api_keys.py`)

- Extend `PHASE_SCOPES` and `ADMIN_SCOPES` with `trackers:write` and `upgrades:write`; Profile offers them to admins.
- `tracker_create` and `tracker_update`: `validate_tracker_core`; an immediate transaction writing only allowlisted columns (fixed column list, parameterised); duplicate repository maps to "already tracked"; strategy or prerelease change calls `reset_release_state(clear_last_checked=True)`; audit on the same connection; no `check_tracker` call; return `check_state`.
- `tracker_update` rejects `repository` and every probe, SSH or binding field by name.
- `tracker_set_enabled`: immediate transaction update and audit.
- `tracker_delete`: in one immediate transaction count events and decisions, delete, and audit.
- `upgrade_save_review`: `save_upgrade_decision(mark_deployed=False)`; conflicts become `ToolError` messages naming the current `release_key` and `revision`.
- Tests: section 10 items T12 to T15.

### Phase 2 completion criteria and Gate 2

As for Phase 1, plus every P2.2 browser regression test passes. The independent reviewer checks the extracted helpers and the browser upgrade flow specifically.

## 8. Concurrency and transaction requirements

- Every MCP read-then-write uses `transaction(immediate=True)`.
- Audit for a data write shares the write's connection. Denials, external operations and 401 throttling events do not share a connection with anything; 401s are logged at INFO without credentials and are not written to `audit_log`.
- Leases are released only by the thread that ran the work, or by expiry.
- No module-level mutable principal state. The principal comes from `get_access_token()` or the middleware context per request.
- One uvicorn worker. SQLite busy timeout stays at 30 seconds.

## 9. Test environment requirements

- Follow the existing pattern (`tests/test_security_remediations.py`): `tempfile.TemporaryDirectory()`, `RADAR_DB` pointing inside it, test `SECRET_KEY` and `ENCRYPTION_KEY`, and environment restored in `tearDown`.
- Outbound services are mocked so that any unexpected call fails the test:
  - GitHub: `radar.checker.get_latest`.
  - Probes: `radar.probes._connect`, `radar.probes._http_get`, `radar.probes.subprocess.run`.
  - Inventory: `radar.probes.sync_inventory` and `radar.checker.sync_inventory`, both raising if called.
  - Notifications: `radar.notifications` SMTP and Pushover send functions.
  - Model: `radar.auto_analysis.chat`.
- Secret canaries: unique strings planted in the admin password, encrypted SMTP, Pushover, OpenAI, Dockhand and Portainer secret settings, a user's Pushover key, `GITHUB_TOKEN`, a reset token and an API key secret. Responses, errors, audit rows and captured logs (`assertLogs` on the root logger) must not contain any canary.
- The real-HTTP test starts uvicorn on an ephemeral port in a background thread inside the test and connects with the SDK `Client`. No external network.

## 10. Requirement to test map

| ID | Requirement | Test (file) |
|---|---|---|
| T1 | SDK client initialises, lists tools and calls `radar_status` over real HTTP with a key | `tests/test_mcp_server.py` |
| T2 | Missing, malformed, wrong, expired, revoked, disabled-user, deleted-user, password-changed keys get 401 | `tests/test_mcp_server.py` |
| T3 | Plain HTTP with `Host: localhost` refused unless `RADAR_MCP_ALLOW_HTTP=true`; forwarded proto from an unlisted peer ignored; listed peer honoured | `tests/test_mcp_server.py` |
| T4 | Disallowed Host gets 421, disallowed Origin 403, missing Origin accepted; body over 128 KiB gets 413 | `tests/test_mcp_server.py` |
| T5 | Invalid-auth throttle returns 429 with `Retry-After`; a valid key from the same address still succeeds | `tests/test_mcp_server.py` |
| T6 | Non-admin and read-only keys: hidden tools absent from tools/list; direct calls return the unknown-tool error; denial audited without arguments | `tests/test_mcp_server.py` |
| T7 | `tracker_check` never probes or syncs; dispatches notifications only for a new event; auto-analysis only when enabled; deferred under shared cooldown with no GitHub call | `tests/test_mcp_operations.py` |
| T8 | `tracker_probe` never syncs; inventory mode reports cached source; unconfigured tracker makes no contact | `tests/test_mcp_operations.py` |
| T9 | Lease held until the operation returns, even after the client gives up; concurrent same-tracker call refused; expired lease reclaimed; caps enforced | `tests/test_mcp_operations.py` |
| T10 | Multi-process `enqueue_sync` creates one job; audit and job roll back together | `tests/test_mcp_operations.py` |
| T11 | Demoted admin loses operations tools immediately | `tests/test_mcp_operations.py` |
| T12 | Tracker create and update make no outbound call; repository and probe fields rejected; unknown fields rejected; `check_state` correct after create, ordinary edit, source change, disable | `tests/test_mcp_writes.py` |
| T13 | `tracker_delete` requires confirm and reports counts | `tests/test_mcp_writes.py` |
| T14 | Upgrade release binding, stale revision and deployed immutability via MCP and browser, including a two-process race | `tests/test_mcp_writes.py` |
| T15 | Phase 2 scopes cannot be created or used before P2.3 | `tests/test_api_keys.py` |
| T16 | Profile key lifecycle, CSRF, one-time display, `no-store`, cookie free of secret | `tests/test_api_keys.py` |
| T17 | Secret canaries absent everywhere | `tests/test_mcp_server.py` |
| T18 | Existing browser login, CSRF, profile, tracker and upgrade tests unchanged and passing | existing suite |

## 11. Dependency constraints and revalidation

- Proposed constraint: `mcp>=2.3.0,<2.4`. The minor-version ceiling exists because SDK middleware is provisional.
- If implementation starts after 2.3.0 is no longer current, before writing code:
  1. Read the PyPI release history and the SDK changelog for every 2.3.x patch and any newer minor version.
  2. Prefer the newest 2.3.x patch. Move to a newer minor version only if its changelog shows no middleware, auth or transport change affecting this design, and record that decision for the owner.
  3. Repeat every P1.0 compatibility check against the chosen version.
- In the disposable environment, `pip install -r requirements.txt` must resolve with the existing pins, and `pip check` must pass. Confirm `cryptography<51` satisfies `pyjwt[crypto]`.
- Record the added distributions (`pip freeze` difference) and the image size change from `docker image ls` before and after.

## 12. Validation commands and expected outcomes

Run from the repository root.

```bash
python -m unittest discover -s tests -v
```

Expected: every test passes; total equals the P1.0 baseline plus the new tests.

```bash
docker compose config
```

Expected: succeeds without any MCP variable set; `radar`, `scheduler` and `portainer-worker` render identically to the baseline (compare with output saved in P1.0).

```bash
docker compose --profile mcp config
```

Expected: succeeds and includes the `mcp` service bound to `127.0.0.1:9121`.

```bash
docker compose build
```

Expected: image builds; inside it `python -c "import mcp, importlib.metadata as m; print(m.version('mcp'))"` prints a 2.3.x version, and `pip check` reports no broken requirements.

Isolated smoke test, with a disposable Compose project name and volume and placeholder secrets generated for the test only:

```bash
docker compose -p radar-mcp-smoke --profile mcp up -d
```

Expected: `radar` healthy on `/healthz`; `mcp` healthy on its own `/healthz`; an unauthenticated POST to `/mcp` returns 401; plain HTTP is refused unless the smoke test sets `RADAR_MCP_ALLOW_HTTP=true`; with a key created through the browser Profile page of the smoke instance, the SDK client lists only the tools for that key.

```bash
docker compose -p radar-mcp-smoke --profile mcp down -v
```

Expected: the disposable project and volume are removed. Never run `down -v` against the owner's real project.

Report any command that cannot run (for example, Docker unavailable) as not verified, with the reason.

## 13. Browser compatibility and security regression checks

- Login, logout, password reset, CSRF rejection, security headers, CSP and rate-limited login behave as before (existing tests).
- Profile update still works and still rebinds the session stamp.
- Tracker add, edit (including repository change deleting events), toggle, delete, check, probe, bulk actions and inventory sync behave as before, apart from enqueue deduplication.
- Upgrade save, historical notes and mark-deployed work. Stale or moved-release submissions are refused (Phase 2, intended change).
- `/healthz` on the web service is unchanged.

## 14. Known limitations

As listed in the design: duplicate notification possible when dispatches race for the same event; a stuck inventory job blocks syncs; no OAuth-only clients; one worker; lost responses after timeout or disconnect; last write wins for tracker descriptive fields edited at the same time in browser and MCP (no revision on trackers).

## 15. Owner decisions still open

| Decision | Recommended default | Consequence of the default |
|---|---|---|
| Accept the two browser-visible changes (enqueue deduplication now; stale upgrade forms refused in Phase 2) | Accept | Browser users may see "already queued" more reliably and a refusal when a release moved while editing |
| `tracker_check` on disabled trackers | Allow, matching the browser | Agents can check paused trackers manually; the scheduler still skips them |
| Operation limits (section 3 defaults) | 1 per key, 2 global, 20 per hour | Agents doing large sweeps are throttled; adjust by environment variable |
| Hermes protocol support | Verify with the owner's Hermes version during stage C; both protocol generations are served | If Hermes needs OAuth or sessions, it cannot connect until a later change |
| Release version for Phase 1 | Decide at stage B (suggest 2.11.0) | None until release |

## 16. Installation and rollback runbook (stage C only)

Not authorised by this plan. Requires separate owner approval at the time. The owner performs key creation, credential handling and proxy changes. The agent may prepare commands and verify, but must not run stage C steps without that approval. Values in angle brackets are placeholders and must not be committed with real values.

Preflight:

1. Confirm the released image tag `<release-version>` contains Phase 1 (and Phase 2 if approved), and its release notes were reviewed.
2. On the deployment host: `git status`, current image tag, `docker compose ps`; record the current version for rollback.
3. Back up: `./scripts/backup.sh` (online backup with integrity check). Confirm the backup file exists outside the repository.

Configuration (owner edits `.env` on the host):

```bash
RADAR_MCP_BIND_ADDRESS=127.0.0.1
RADAR_MCP_PORT=<mcp-host-port>
RADAR_MCP_ALLOWED_HOSTS=<public-mcp-hostname>,<public-mcp-hostname>:*
RADAR_MCP_FORWARDED_ALLOW_IPS=<proxy-peer-address-or-network>
RADAR_MCP_ALLOW_HTTP=false
```

Startup:

```bash
docker compose pull
```

```bash
docker compose --profile mcp up -d
```

Health:

- `docker compose ps` shows `radar` and `mcp` healthy.
- `curl -fsS http://127.0.0.1:<mcp-host-port>/healthz` on the host returns `{"status":"ok"}` (adjust the Host header per the P1.0 finding).
- The web `/healthz` is unchanged.

Proxy (owner): route `https://<public-mcp-hostname>/mcp` to `127.0.0.1:<mcp-host-port>`, overwrite `X-Forwarded-For` and `X-Forwarded-Proto`, and pass the original Host. Do not publish the backend port publicly.

Client connection (owner):

1. In Profile, create a read-only key named for the client. Store it in the client's secret store or environment, never in a repository.
2. Configure Hermes with URL `https://<public-mcp-hostname>/mcp` and header `Authorization: Bearer ${RADAR_MCP_KEY}`.
3. Verify the client lists only read tools and `radar_status` returns the expected version.
4. Only then, if wanted, create an admin key with `operations:run` and verify one `tracker_probe` on a non-critical tracker.

Rollback:

- MCP only: `docker compose stop mcp` and `docker compose rm -f mcp`, or start without `--profile mcp`. Revoke keys in Profile. The browser is unaffected.
- Whole release: set `RADAR_VERSION` to the recorded previous version and `docker compose up -d`. The additive schema is ignored by the previous version (proven in P1.10). Restore the backup with `scripts/restore.sh <backup> --confirm` only if data damage is found, because restore discards changes made since the backup.
- Remove the proxy route (owner).

## 17. OpenChamber handoff

Paste into OpenChamber when the owner is ready to authorise a stage:

```text
Repository: SRR-01-Software-Release-Radar-Community-Growth (baseline main 6624d4d, v2.10.9).
Read first: AGENTS.md, docs/superpowers/specs/2026-10-31-built-in-mcp-design.md (revision 3) and docs/superpowers/plans/2026-10-31-built-in-mcp-implementation-plan.md.

Authorised stage: <A1 | A2>. Nothing else is authorised.
- Do only that stage's tasks on a local feature branch, starting with P1.0 (or P2 tasks after Gate 1 acceptance).
- Use temporary databases and mocked outbound services only. No live data, credentials, production hosts or real notifications.
- Do not commit, push, open pull requests, merge, publish images, change versions, install on any host, create keys or change proxies unless I authorise that specific action.
- If HEAD differs from 6624d4d in any file the plan names, or a P1.0 compatibility check fails without a listed fallback, stop and report.
- Finish with STATUS, CHANGES, VALIDATION (exact commands and results, including anything not verified) and BLOCKERS / NEXT STEP, then stop and wait for the gate review.
```
