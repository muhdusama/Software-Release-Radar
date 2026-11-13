# Built-in authenticated MCP Implementation Plan

**Ready for plan review:** the owner explicitly selected "Revision 3 (Recommended)" after the design conflict was explained. Revision 3 governs, including removal of settings tools and separate phase approvals. This implementation plan remains unapproved; the earlier draft is preserved. No product implementation or deployment has started.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the complete approved two-phase, optional authenticated MCP service, with browser-only key management, constrained operations and data writes, independent security review, and separately gated production verification and YouTrack evidence.

**Architecture:** Keep Flask/Gunicorn, scheduler, inventory worker and SQLite. Run the official SDK in one optional ASGI/uvicorn process, using its native authentication, transport security, typed tools and middleware. Add only application-specific key verification, bounds, projections and SQLite counters/leases; share the narrow transaction, inventory enqueue and upgrade-review integrity fixes with browser callers.

**Tech Stack:** Python 3.13, Flask, SQLite WAL, official `mcp>=2.3.0,<2.4`, SDK-installed ASGI/uvicorn dependencies, Docker Compose, `unittest`, existing GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-31-built-in-mcp-design.md` (revision 3, original body preserved; dated owner-authorised rollout addendum records later approval).

## Global Constraints

- `mcp>=2.3.0,<2.4`.
- `stateless_http=True`, `json_response=True`, endpoint `/mcp`.
- Optional Compose service `mcp` (profile `mcp`), same image and SQLite volume, started with `python -m radar.mcp_server`.
- One uvicorn worker on container port 8081. Existing installations start exactly as before without the profile.
- API keys are the only MCP credential. No OAuth service and no password exchange endpoint.
- Never return passwords, password hashes, API keys, encrypted secrets, reset tokens, session material or private SSH key material.
- No settings tools, bulk operations, check-all or probe-all, imports, notification tests, user, key or credential tools.
- No arbitrary commands or SQL, role management, integration credential replacement, or software deployment tools.
- Browser and scheduler behaviour is not changed, except the approved shared inventory deduplication and upgrade-review integrity fixes.
- Phase 1 keys can only hold `read` and `operations:run`. Phase 2 scopes are not offered, not storable and ignored at verification until Phase 2 is approved and shipped.
- Expiry defaults to 90 days, at most 365 days. Last-used time is updated at most once a minute.
- Profile key management is CSRF protected. Creation requires the current password; secret rendered once in the POST response with `Cache-Control: no-store`, never flashed.
- `RADAR_MCP_ALLOWED_HOSTS` required; `RADAR_MCP_ALLOWED_ORIGINS` defaults to empty; CORS stays disabled.
- Empty `RADAR_MCP_FORWARDED_ALLOW_IPS` disables proxy headers entirely. No `TRUST_PROXY_HEADERS` or `ProxyFix` for MCP.
- Require `scope["scheme"] == "https"` except `/healthz`, unless explicit `RADAR_MCP_ALLOW_HTTP=true`; never infer security/locality from Host, Origin or client address.
- `transaction(immediate=True)`, transactional audit and revision checks preserve cross-process integrity. Additive, idempotent migrations only; no table/column drops on rollback.
- Python 3.13; Australian English, no em dashes or contractions in public copy. No private deployment details, real secrets or backups in Git or evidence.

## Review Focus

- Revocation/password reset/demotion between discovery and dispatch: re-read authority at dispatch, hide inaccessible tools identically to unknown names (Task 2/4).
- Chunked bodies, mismatched lengths and spoofed forwarding headers: size actual bytes before SDK parsing, ignore untrusted forwarding data, protect custom routes too (Task 3).
- Disconnect after external side effect: keep thread lease through outcome audit; never pretend cancellation undoes work (Task 5).
- Populated databases with secret canaries in cached errors and inventory labels: never dump rows or upstream exceptions; preserve non-admin destination redaction (Task 4).
- Same-second stale review or save racing mark-deployed: release binding plus integer revision and immediate transactions, not timestamp comparison (Task 7).

---

## Authority, sequencing and stop points

Baseline inspected: `main`, HEAD `6624d4d2a2f03956a0cfc2397e064f461aaef6a1`, version 2.10.9. Dispatch reported the design as the only untracked input; actual inventory correction follows. No product changes, installation, branch, commit or deployment is performed by this planning call.

Inventory correction from read-only exploration: an older untracked `docs/superpowers/plans/2026-10-31-built-in-mcp-implementation-plan.md` also exists (modification time predates this call). It has been read in full and is preserved, not deleted or overwritten. This new exact plan supersedes its handoff only after owner approval. Retained details include keyset pagination, tag/query/since/linked filters, check/probe confirmation, notification summaries, deletion counts, read-required keys and audit key attribution. Explicit corrections proposed for exact-plan approval: use existing checklist limits 30 items of 240 characters rather than the old draft's 50/300 (the actual browser validator already enforces 30/240); use existing tag normalisation ceiling 12 rather than old draft 20; never forward raw cached exception text even if capped; enforce one tracker lease across both check and probe (not the old draft's per-tool uniqueness); loopback-only published MCP binding. These are visible validation/security reconciliations, not silently omitted functionality.

Owner approved the original design, then said **"Approved. implement, deploy and record in youtrack"**, and subsequently explicitly selected **"Revision 3 (Recommended)"**. This resolves design authority and preserves the deployment request, but does not approve this exact implementation plan or its digest. `.dev/tasks/SRR01-4.json` is `ready` / `awaiting_plan_approval`, both approvals pending. Live execution issue: https://youtrack.home.mmusama.com/issue/SRR01-4. Issue updates must be recorded and read back through the configured identity.

1. Ask for exact-plan/digest approval and execution-method selection before implementation. Recommend **one implementer specialist, coordinator native supervision, then an independent `claudex_reviewer` security review and independent Codex evidence assessment**. No parallel writers. Native execution is also available; neither method has been selected. This call spawns nobody.
2. Confirm focused development-branch authority before changing product code; do not implement directly on main. Actual contract branch remains main until authorised branch creation is recorded and the contract rebound for approval if covered fields change.
3. Phase 1 ends at an independent review gate. Phase 2 is included, not dropped: exact-plan approval must explicitly cover both phases; stop before Phase 2 if approval is Phase-1-only. Phase-2 scopes are enabled only with its reviewed implementation.

The owner must accept the Phase-1 review result and authorise the Phase-2 start before it begins, even if the overall exact plan is approved now. Gate acceptance is not implied by a reviewer pass alone.
4. `docs/GITHUB-WORKFLOW.md` requires branch, PR, passing CI, review and merge before production. Obtain **specific commit/push/PR/merge authority**; deployment language alone does not grant these actions. No tag, release publication or GHCR publication is implied.
5. Production deployment is requested, but execution remains blocked until the owner identifies the host, checkout, access route, existing proxy arrangement, approved revision and maintenance window privately. No host is inferred. No DNS, networking, proxy edits, new credential provisioning or live data restoration is authorised. If the existing route cannot safely serve MCP, report that blocker rather than changing infrastructure. Local implementation can proceed after gates 1/2 without production facts.

## Concrete file map and existing call graph

- Modify `requirements.txt`: the one approved SDK dependency. Do not independently pin transitive dependencies without resolver evidence and renewed approval.
- Modify `radar/db.py`: `transaction(immediate=False)`, `audit(..., conn=None)`, additive MCP tables; later `upgrade_decisions.revision`.
- Modify **`radar/portainer_jobs.py`**, not its neutral re-export `radar/inventory_jobs.py`: this is where `enqueue_sync` lives. Browser `/portainer/sync` and MCP import the same function. Leave import jobs/worker crash recovery unchanged.
- Create `radar/mcp_auth.py`: key lifecycle and SDK `TokenVerifier`, effective scopes and fresh principal lookup; no password endpoint.
- Modify `radar/web.py` Profile and create/revoke routes; modify `radar/templates/profile.html`: current logged-in owner only, CSRF, one-time key response, metadata list.
- Create `radar/mcp_server.py`: `build_server`, SDK middleware, small ASGI guard, startup and uvicorn entry point; no Flask coupling.
- Create `radar/mcp_tools.py`: explicit tool registrations, typed inputs, bounded SQL projections, dispatch transaction/counters/leases and safe public error mapping. Keep the finite tool policy here rather than build a generic registry framework.
- Modify `radar/upgrade_workflow.py`, `radar/web.py:upgrade_decision`, `radar/templates/upgrade_decision.html`: shared atomic release/revision-bound save; browser-only mark-deployed.
- Modify `radar/tracker_utils.py` and the browser tracker form's core validation/reset calls only: share approved tracker validation and release-state reset while preserving browser immediate check and repository-change history deletion.
- Modify `docker-compose.yml`, `.env.example`, `README.md`, `docs/DOCKER.md`, `docs/GITHUB-WORKFLOW.md`, `.github/workflows/ci.yml`; create `docs/MCP.md`: optional service, security model, supported connection examples, side effects, human key management and rollback. No version bump/tag publishing in this task without release authority.
- Modify existing `docs/CONFIGURATION.md`, `docs/SECURITY-CONTROLS.md`, `docs/ARCHITECTURE.md` and add an unreleased `CHANGELOG.md` entry, retaining the established documentation surface from the older draft. No release version selected by this plan.
- Create `tests/test_mcp_sdk.py`, `tests/test_mcp_auth.py`, `tests/test_mcp_transport.py`, `tests/test_mcp_reads.py`, `tests/test_mcp_operations.py`, `tests/test_mcp_writes.py`, `tests/test_upgrade_concurrency.py`, `tests/test_mcp_http.py`; extend `tests/test_radar.py` for browser forms; create `tests/test_inventory_enqueue_concurrency.py`.
- Create later, **not during planning**, `scripts/mcp_acceptance.py` (isolated Compose lifecycle and SDK smoke) and `scripts/mcp_deploy_verify.py` (read-only deployment verification, never deployment/credentials). Their exact CLI contracts are below.
- Create during execution `.dev/tasks/SRR01-4.evidence.json` and sanitised `.dev/reviews/SRR01-4-{phase1,security,codex}.json`; no invented pass records now.

Read before editing: `radar/db.py`, `auth.py`, `auth_rate_limit.py`, `web.py`, `security_controls.py`, `tracker_utils.py`, `checker.py`, `probes.py`, `auto_analysis.py`, `notifications.py`, `portainer_jobs.py`, `inventory_jobs.py`, `portainer.py`, `upgrade_workflow.py`, existing scheduling/security/notification/inventory tests, Docker files and GitHub workflows. Existing test fixtures use a `TemporaryDirectory`, patched `RADAR_DB`, generated local encryption key, seeded password hash and Flask `test_client`. Follow that pattern, no production database.

Flow: Profile -> key rows -> SDK verifier (every HTTP request) -> message middleware (discovery/call hiding) -> typed tool -> immediate transaction (fresh principal, scope, quota, lease) -> existing helper -> safe projection -> audit. `check_tracker` -> GitHub -> `_record_success` -> optional `auto_analyse_event`; MCP dispatches `dispatch_release_notifications([event_id])`. `probe_tracker(..., refresh_portainer=False)` uses stored destinations/cached inventory. `enqueue_sync` uses `portainer_sync_jobs`, served by the existing inventory worker. Browser upgrade POST and MCP save converge on one new helper.

## Exact tool interface and data contract

All tools are synchronous `def` functions registered with `MCPServer`; SDK owns threading, JSON-RPC and argument parsing. No resources, prompts or arbitrary dispatch tool. Positive identifiers use strict integers (`bool`/numeric strings refused); booleans are strict. Typed models forbid extra arguments/fields. `Principal` is an immutable dataclass with `key_id: str`, `user_id: int`, `is_admin: bool`, `scopes: frozenset[str]`; never holds a raw key or password hash. `current_principal(*, conn: sqlite3.Connection | None = None) -> Principal` reads SDK access-token identity then revalidates key/user/password binding in the database.

Every list accepts `limit: int = 25` (1..100) and `after_id: int | None = None` (positive strict integer), returns `{items: list[dict], next_after_id: int | None}` with ascending ID keyset ordering (`WHERE id > ? ORDER BY id LIMIT limit+1`) and lookahead. Reads are cached only: **`releases_list` reads stored events, never `get_recent_releases`**; current release body is available through `tracker_get`. List pages are not snapshots; later insertions can appear on subsequent pages, but earlier rows never repeat. No offset or unbounded fetch-all. `query` max 120 characters is literal substring search with SQL wildcard escaping, `tag` max 64 is exact normalised tag membership, `since` is a validated ISO calendar date filtering event detection timestamps; all SQL values parameterised and selectable columns/order fixed in code.

Exact tool signatures (return `dict[str, object]`; `Page` below means the envelope above, not a new service):

```python
radar_status() -> dict[str, object]
trackers_list(limit: int = 25, after_id: int | None = None, enabled: bool | None = None, tag: str | None = None, query: str | None = None) -> dict[str, object]
tracker_get(tracker_id: int) -> dict[str, object]
releases_list(tracker_id: int, limit: int = 25, after_id: int | None = None) -> dict[str, object]
history_list(limit: int = 25, after_id: int | None = None, tracker_id: int | None = None, since: str | None = None) -> dict[str, object]
upgrades_list(limit: int = 25, after_id: int | None = None, decision_status: str | None = None) -> dict[str, object]
upgrade_get(tracker_id: int, release_key: str | None = None) -> dict[str, object]
inventory_list(limit: int = 25, after_id: int | None = None, linked: bool | None = None) -> dict[str, object]
inventory_summary() -> dict[str, object]
job_get(job_id: int) -> dict[str, object]
tracker_check(tracker_id: int, confirm: bool) -> dict[str, object]
tracker_probe(tracker_id: int, confirm: bool) -> dict[str, object]
inventory_sync() -> dict[str, object]
tracker_create(tracker: TrackerCreate) -> dict[str, object]
tracker_update(tracker_id: int, changes: TrackerPatch) -> dict[str, object]
tracker_set_enabled(tracker_id: int, enabled: bool) -> dict[str, object]
tracker_delete(tracker_id: int, confirm: bool = False) -> dict[str, object]
upgrade_save_review(tracker_id: int, release_key: str, expected_revision: int, review: UpgradeReview) -> dict[str, object]
```

Discovery and execution require `read` for the first ten tools. `inventory_list`, `inventory_summary`, `job_get` additionally require **current admin**. The next three require `operations:run` plus current admin. Tracker mutations require `trackers:write` plus current admin. Review save requires `upgrades:write` plus current admin. All issued keys require `read`; no scope implicitly grants another scope, and planted write-only rows fail verification. Check/probe require literal `confirm=true` (strict boolean), not a truthy string. Use identical unknown-tool text/code for inaccessible and nonexistent tools. No key can enlarge authority via tool parameters. `radar_status` reports only `name,version,commit,github_cooldown_until,server_time`, no settings/environment/paths.

ToolAnnotations: reads `readOnlyHint=true,destructiveHint=false,openWorldHint=false`; check `readOnlyHint=false,idempotentHint=false,openWorldHint=true`; probe `readOnlyHint=false,idempotentHint=true,openWorldHint=true`; enqueue `readOnlyHint=false,idempotentHint=true,openWorldHint=false`; create/review save not idempotent; update/enable idempotent; delete destructive and not read-only. These hints never replace permission/confirmation checks. Tests inspect annotations and descriptions for declared side effects and untrusted-content guidance.

`TrackerCreate` exact fields: required `name` (1..120), `repository` (normalised using `normalise_repository`); optional `strategy: Literal['release','tag']='release'`, `include_prereleases: StrictBool=False`, `enabled: StrictBool=True`, `homepage_url: str | None=None` (HTTP/HTTPS URL <=2048), `notes: str | None=None` (<=4000), `tags: list[str]=[]` (<=12 of <=32, normalise using `normalise_tags`), `refresh_hours: int | None=None` (existing `ALLOWED_REFRESH_HOURS`, null on create uses configured browser default), `installed_version: str | None=None` (<=100). `TrackerPatch` has the same fields, all optional/unset distinguished from explicit null; **repository excluded**; reject empty changes and null for non-nullable fields. Probe configuration, machine/destination, SSH fields and inventory bindings are not writable through MCP. Use `probe_mode='manual'` on creation. These restrictions leave all approved ordinary edits available without adding credential or remote-command management.

`UpgradeReview` exact fields: `decision_status: Literal['review','update','wait','ignore']='review'`, `priority: Literal['low','normal','high','urgent']='normal'`, `risk: Literal['unknown','low','medium','high','critical']='unknown'`, `maintenance_date: str | None=None` (existing date validator), `checklist: list[ChecklistItem]=[]` (<=30; `{text: str(1..240), done: StrictBool}`), `rollback_notes: str | None=None` (<=10000), `change_record_url: str | None=None` (<=2048; existing HTTP/HTTPS/obsidian validator), `decision_notes: str | None=None` (<=10000). Required `release_key` is nonempty <=240; `expected_revision` >=0, strict integer. No deployed status, deployed version/time, action or installed-version override accepted.

Output allowlists:

- TrackerSummary: `id,name,repository,strategy,include_prereleases,enabled,homepage_url,tags,refresh_hours,current_version,current_release_name,current_published_at,installed_version,detected_installed_version,last_checked_at,last_status,last_error,last_probe_at,last_probe_status,last_probe_latency_ms,check_state,next_due_at,deferred_until`. `tracker_get` adds `notes,current_release_url,current_release_body`. Admin adds nested `probe` with `machine_name,install_host,install_port,install_scheme,probe_mode,health_path,version_probe_path,version_json_path,version_regex,ssh_user,ssh_port,ssh_key_name,docker_container,portainer_service_id,last_probe_error` only. SSH key filename is metadata, never read/return key contents. Errors are fixed public failure summaries, never cached exception text.
- Release: `id,version,release_name,previous_version,release_url,published_at,detected_at,notified,release_body`. History adds `tracker_id,tracker_name` and excludes bodies. Label all free text as untrusted data, never instructions.
- Upgrade list: `id,tracker_id,tracker_name,release_key,release_name,revision,decision_status,priority,risk,maintenance_date,updated_at`. Detail/save adds `historical,checklist,rollback_notes,change_record_url,decision_notes,installed_version_at_decision,previous_version,deployed_version,deployed_at`; unsaved current decision revision 0. No user row joins or analysis/session material.
- Inventory: `id,provider,environment_name,container_name,image,state,present,detected_version,linked_tracker_id,updated_at`. No raw labels, payload JSON, endpoint URLs, credentials or arbitrary provider metadata. Summary returns provider label, last sync time/status, fixed safe sync-error summary and environment/service/linked/offline counts. Admin-only environment names are bounded but not raw endpoint URLs.
- Job: `id,status,requested_at,started_at,completed_at,total_environments,processed_environments,services_found,offline_environments,unexpected_errors,message,error`; message/error are fixed public status summaries, never worker ID, raw provider text or current environment details.
- Check: `status,changed,baseline,version,event_id,notifications{sent,failed,skipped},deferred_until,error`. Probe: `status,online,installed_version,latency_ms,source_kind` (`live` or `cached_inventory`), `inventory_synced_at` (cached only), `provider,error`. Inventory sync `{job_id,reused,status}`. Delete `{tracker_id,deleted:true,events_deleted,decisions_deleted}` only after confirmation; count/delete/audit in one transaction. Create/update return `tracker_id,check_state` plus allowed current tracker projection.

Strings max 10000 characters, tracker notes/release-list bodies max 4000, detail release bodies max 8000, public errors max 500, versions/names max 240 (tracker name 120), URLs max 2048; truncate reads with `truncated=true,truncated_fields`, reject oversize writes. Every serialised result <=256 KiB UTF-8: construct bounded projections before serialising, reduce list items and set `next_after_id` to the last emitted ID when byte limit would be exceeded; an individual item must fit or return fixed tool error. Never return raw row dictionaries, settings, user data, analysis context, token digests or outbound exception text. Canary tests plant known secrets in credential/error/labels fields and capture responses/protocol errors/audit/logs, not intentionally user-authored notes (not a general secret scanner for user content).

MCP-only limits, stored/shared across processes in SQLite: `MCP_KEY_MINUTE_LIMIT=120` authenticated messages/key/minute (discovery included); `MCP_OPERATION_HOURLY_LIMIT=20` calls/key/hour; `MCP_OPERATION_KEY_CONCURRENCY=1`, `MCP_OPERATION_GLOBAL_CONCURRENCY=2`, plus 1 per tracker across check/probe; `MCP_OPERATION_LEASE_SECONDS=300`, expiry for process-failure recovery only. `MCP_AUTH_FAILURE_LIMIT=20` invalid attempts/source/10 minutes. Preserve these documented operator knobs, parse with existing `_int_env` (positive ranges: key 1..10000, operations 1..1000, key concurrency 1..4, global 1..16, lease 300..3600, auth failures 1..1000). Additional fixed 30 data writes/key/minute and 200 invalid attempts/global/10 minutes; valid keys from a throttled address/global window still pass normal authenticated quotas. HMAC source bucket keys with `SECRET_KEY`, no raw address stored; bounded cleanup. Request body cap **128 KiB** actual bytes, reject declared oversized lengths immediately, malformed length rejected, streamed bytes bounded even with no header. SDK errors expose only approved static messages and retry timestamps; no stack traces. Do not return a running-thread timeout. Before approving crash expiry, Task 5 verifies the real worst-case fan-out bound; if it can exceed configured expiry, **stop/replan** lease duration or heartbeat, never allow premature reuse.

Schema detail: `mcp_rate_counters(key TEXT PRIMARY KEY,requests INTEGER NOT NULL,expires_at TEXT NOT NULL,updated_at TEXT NOT NULL)` with expiry index; `mcp_operation_leases(id TEXT PRIMARY KEY,key_id TEXT NOT NULL,user_id INTEGER NOT NULL,tool TEXT NOT NULL,tracker_id INTEGER,expires_at TEXT NOT NULL,created_at TEXT NOT NULL)` with expiry/key indexes and unique non-null `tracker_id` across tools. Add nullable `audit_log.api_key_id TEXT` without foreign key so key audit survives lifecycle changes. Extend `audit(..., *, conn=None, api_key_id: str | None=None)`; every MCP success/dispatch/outcome/denial records key attribution and user/tool/target/outcome without arguments, token or destination text. 401 attempts are counted and logged safely, not one audit row per brute-force attempt. Key creation/revocation audits share key-write transactions.

## Task 1: SDK compatibility and shared atomic primitives (Phase 1)

**Files:** `requirements.txt`, `radar/db.py`, `radar/portainer_jobs.py`; create `tests/test_mcp_sdk.py`, `tests/test_inventory_enqueue_concurrency.py`.

**Interfaces:** `transaction(immediate: bool = False) -> Iterator[sqlite3.Connection]`; `audit(user_id, action, target_type=None, target_id=None, details=None, *, conn: sqlite3.Connection | None = None, api_key_id: str | None = None) -> None`; `enqueue_sync(requested_by: int | None = None, *, conn: sqlite3.Connection | None = None) -> tuple[int, bool]`. Existing callers remain valid; supplied connections are neither committed nor closed by helpers.

- [ ] Before product edits run `git status --short --branch`, `git rev-parse HEAD`, `python -m unittest discover -s tests -v` and save the actual test count. Require authorised development branch and unchanged named baseline functions. Use a disposable Python 3.13 virtual environment, never install into the system interpreter; capture `python -m pip freeze` before/after and image-size change. Recheck PyPI/official 2.3.x patch changelogs and retain `<2.4`; moving minor version requires renewed approval.

- [ ] Write `SDKCompatibilityTests` against the **installed** SDK: import `MCPServer`, construct native verifier+AuthSettings, real client initialise/list/call, strict extra-field rejection, access token context in middleware and sync tools, custom-route Host/Origin handling, protocol stateless/json options, and uvicorn exact-peer/CIDR parsing. Assert package version in 2.3.x and resolver health. Record actual protected-resource metadata; do not invent a functioning OAuth authority.
- [ ] After installation is authorised, run `python -m pip install -r requirements.txt` and `python -m pip check`, then `python -m unittest discover -s tests -p 'test_mcp_sdk.py' -v`. Before the dependency edit, failure is missing SDK; after, all compatibility assertions must pass. Missing required AuthSettings fields: supply only fields required by installed documentation, document inert metadata. Extra args accepted: forbid extras on typed tool models and middleware parameter validation. Token unavailable in middleware: verified SDK request context only, never caller-supplied identity. CIDR unsupported: require exact peers. Custom routes bypass security: outer guard applies Host/Origin before every route. If the SDK cannot support documented filtering/authentication without bespoke protocol or weakening policy, stop and replan, not switch SDK generations silently.
- [ ] Add atomicity regression test (test imports shown; fixture sets temporary `RADAR_DB` and calls `init_db`):

```python
from radar.db import audit, connect, transaction
from radar.inventory_jobs import enqueue_sync

def test_enqueue_and_audit_rollback(self):
    with self.assertRaises(RuntimeError):
        with transaction(immediate=True) as conn:
            job_id, created = enqueue_sync(conn=conn)
            self.assertTrue(created)
            audit(None, 'mcp_inventory_sync', 'job', job_id, conn=conn)
            raise RuntimeError('abort')
    with connect() as conn:
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM portainer_sync_jobs').fetchone()[0], 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='mcp_inventory_sync'").fetchone()[0], 0)
```

- [ ] Add spawn-context multiprocess test: eight child processes share only the temporary file path, wait on a multiprocessing event, call `enqueue_sync`, send `(id,created)` through Queue; join with 35-second bounds, assert exit codes 0, one unique ID, exactly one `created=True`, one active DB row. Repeat for direct browser-style `enqueue_sync()` and caller-supplied immediate transaction.
- [ ] Run `python -m unittest discover -s tests -p 'test_inventory_enqueue_concurrency.py' -v`, see signature/duplicate regression failure; implement `BEGIN IMMEDIATE` at transaction entry, audit connection reuse, queue helper connection reuse. Rerun that command and complete existing inventory tests.
- [ ] Run full suite; inspect diff. Prepare a focused commit only after specific commit authority, using `git add requirements.txt radar/db.py radar/portainer_jobs.py tests/test_mcp_sdk.py tests/test_inventory_enqueue_concurrency.py` then `git commit -m "feat: establish MCP SDK and atomic inventory enqueue"`. Do not run these commands during planning or without branch/commit authority.

## Task 2: Browser-only key lifecycle and SDK principal (Phase 1)

**Files:** `radar/db.py`, new `radar/mcp_auth.py`, `radar/web.py`, `radar/templates/profile.html`, new `tests/test_mcp_auth.py`.

**Interfaces:** `create_key(user_id: int, current_password: str, label: str, scopes: list[str], expires_days: int = 90) -> tuple[str, str]` returns `(key_id, one_time_token)`; `revoke_key(user_id: int, key_id: str) -> None`; `list_keys(user_id: int) -> list[dict[str, object]]` metadata only; `RadarTokenVerifier.verify_token(token: str) -> AccessToken | None` async SDK method; `current_principal(*, conn=None) -> Principal` as above. Key management helpers are browser-internal, never registered tools.

- [ ] Add temporary-db tests with seeded admin/user and Flask client CSRF extraction; actual core assertions:

```python
def test_one_time_key_is_not_session_data(self):
    key_id, token = create_key(self.user_id, 'correct-horse-battery', 'Hermes', ['read'])
    self.assertRegex(token, r'^srr_[A-Za-z0-9-]+_[A-Za-z0-9_-]+$')
    with connect() as conn:
        stored = dict(conn.execute('SELECT * FROM mcp_keys WHERE id=?', (key_id,)).fetchone())
    self.assertNotIn(token, str(stored))
    self.assertNotIn(token.split('_', 2)[2], str(stored))
    self.assertNotIn(token, str(list_keys(self.user_id)))
    revoke_key(self.user_id, key_id)
    self.assertIsNone(asyncio.run(RadarTokenVerifier().verify_token(token)))
```

Token secret uses URL-safe alphabet; parse with `split('_', 2)` (not last underscore), ID from `secrets.token_hex(8)`, secret `secrets.token_urlsafe(32)`, digest only secret with existing `token_digest`, constant-time compare and password stamp. Test above additionally compare the **full secret from `split('_',2)[2]`** against storage. Reject malformed/oversize (>256 characters), unknown, expired, revoked tokens. No key/token in log, audit or flash.

- [ ] Add browser tests: wrong password/missing CSRF/no login/other owner's revoke refused; label 1..80 escaped; read user cannot request operations/write; missing read scope refused; 0/366-day expiry refused, default 90; repeated GET/list never reveals secret; creation POST `Cache-Control: no-store`, token absent from `Set-Cookie` and session/flash; revoke POST owner check, keys revoked not deleted. Key list metadata allowlist `id,label,scopes,created_at,expires_at,revoked_at,last_used_at`, no digest/stamp. Key create/revoke audits carry owner/key identity transactionally.
- [ ] Add request-by-request tests: inactive/deleted owner, password reset/change, expiry and revocation invalidate old key immediately; demotion strips operations and both writes, read retained only if granted; last-used update once/minute; injected unknown stored scopes ignored. Phase-1 create rejects either Phase-2 scope and verifier ignores planted Phase-2 scope. Re-read user/key during the transaction before dispatch to catch changes after verification.
- [ ] Run `python -m unittest discover -s tests -p 'test_mcp_auth.py' -v` (red). Add idempotent `mcp_keys` table (`id,user_id,label,secret_digest,password_stamp,scopes_json,created_at,expires_at,revoked_at,last_used_at`, FK owner cascade), helpers and current-password CSRF-protected `/profile/mcp-keys` POST and `/profile/mcp-keys/<key_id>/revoke` POST. Existing Profile update remains intact; render secret in a dedicated inline section of Profile, with labelled fields, no-store also on error. Run test command (green) and existing auth/security suites.
- [ ] Prepare focused authorised commit: `git add radar/db.py radar/mcp_auth.py radar/web.py radar/templates/profile.html tests/test_mcp_auth.py && git commit -m "feat: manage MCP bearer keys through Profile"`.

## Task 3: Native HTTP service, transport guards and optional Compose (Phase 1)

**Files:** new `radar/mcp_server.py`, `tests/test_mcp_transport.py`; modify Compose, `.env.example`, `requirements.txt` if Task 1 resolver requires official HTTP serving extras, docs/MCP.md.

**Interfaces:** `build_server() -> MCPServer`; `build_app() -> ASGIApp` (SDK-generated app wrapped by guard); `main() -> None`. `ASGIApp` is the installed ASGI callable type, not a new wrapper framework. `register_tools(server: MCPServer, *, phase: int = 1) -> None` lives in `mcp_tools.py`, Task 4; Task 3 tests build a minimal local SDK tool to isolate transport before integration.

- [ ] Write ASGI tests using the SDK-installed HTTP test client: missing/wrong/empty Host =>421; bad/present Origin =>403; absent Origin accepted; HTTPS required for metadata/MCP/custom routes except liveness; explicit allow-http opt-in; startup without allowed hosts fails; invalid bearer =>SDK 401 and `WWW-Authenticate` without OAuth login promises; cookie/query/argument credentials do not authenticate. Liveness contains status only. Test chunked/no-length 131073-byte body =>413, declared oversized =>413, malformed/negative length =>400, 131072 within limit, no parsing before bounds. Verify unauthenticated error body never echoes token.
- [ ] Add real uvicorn loopback subprocess tests for unlisted/listed proxy peers and spoofed `X-Forwarded-Proto`, `X-Forwarded-For`, `Host: localhost`; test `TRUST_PROXY_HEADERS=true` has no MCP effect. Exact peer test uses loopback fixtures only; do not add production peers. Invalid-auth limit tests assert 21st source and 201st global request throttle within 10 minutes, valid key from same address still succeeds, rolling-window recovery, shared SQLite counters and no raw source/token in audit. Add range/startup tests for every documented limit knob.
- [ ] Run `python -m unittest discover -s tests -p 'test_mcp_transport.py' -v` (red). Configure native `TokenVerifier/AuthSettings`, `TransportSecuritySettings`, SDK `/healthz` and middleware. Guard actual body bytes, HTTPS and invalid-auth attempts; use SDK security mechanism where available and explicitly cover custom routes. Do not add CORS or new auth handlers.
- [ ] Implement optional Compose service using same build/image/data volume and read-only SSH mount, `profiles: [mcp]`, command `python -m radar.mcp_server`, port mapping `127.0.0.1:${RADAR_MCP_PORT:-9121}:8081` (no public bind option in first version), independent 8081 `/healthz` check overriding Dockerfile 8080 check, one uvicorn worker. No dependencies on MCP from existing services. Forward only explicit MCP variables to that service, not the shared environment anchor. Do not use Compose required-variable interpolation for optional MCP hosts; enforce at service startup so profile-off config still works. Health check supplies an allowed Host explicitly, while preserving empty default origins. `.env.example` defaults `RADAR_MCP_ALLOW_HTTP=false`, empty allowed hosts/origins/forwarded peers and the documented numeric defaults. Add `RADAR_MCP_PUBLIC_URL` only if installed AuthSettings requires resource/issuer URL. Example local dev explicitly opts into HTTP and loopback hosts. No wildcard forwarded trust; validate and reject `*`.
- [ ] Run transport tests and `docker compose config` using the isolated acceptance environment created in Task 8, not a real deployment `.env`. Verify without profile mcp absent, with profile present, web health still 8080 and mcp 8081. No secrets in persisted config output.
- [ ] Prepare authorised commit: `git add radar/mcp_server.py tests/test_mcp_transport.py docker-compose.yml .env.example docs/MCP.md && git commit -m "feat: serve optional guarded MCP HTTP endpoint"`.

## Task 4: Bounded read tools, discovery and safe projections (Phase 1)

**Files:** new `radar/mcp_tools.py`, `tests/test_mcp_reads.py`; integrate server middleware.

**Interfaces:** exact read signatures/projections above; `register_tools(server, *, phase=1)`; `current_principal` from Task 2. Reuse `is_due`, `next_due_at`, `parse_utc`, `shared_rate_limit_until`, cached inventory rows; no upstream calls.

- [ ] Write tests through an actual SDK ClientSession for every read tool, complete exact tool-set equality per scope/role, and direct hidden calls versus nonexistent tool equivalence. Plant a secret canary in settings, password/reset/session/credential fields, labels and error messages; seed both admin/non-admin keys. Core assertions (fixture `self.call` returns decoded structuredContent, `self.names` lists SDK tool names):

```python
async def test_nonadmin_inventory_is_unknown_and_secrets_are_absent(self):
    self.assertNotIn('inventory_list', await self.names(self.user_key))
    denied = await self.raw_call(self.user_key, 'inventory_list', {})
    missing = await self.raw_call(self.user_key, 'not_a_tool', {})
    self.assertEqual(denied, missing)
    tracker = await self.call(self.user_key, 'tracker_get', {'tracker_id': self.tracker_id})
    self.assertNotIn('install_host', tracker)
    self.assertNotIn('ssh_key_name', tracker)
    self.assertNotIn(self.canary, json.dumps(tracker))
```

- [ ] Add list tests: 0/101 limits, zero/negative/bool/string after_id, wrong types, extra params, SQL metacharacters, 101+ rows and inter-page inserts, stable keyset ordering/no duplicates, `next_after_id` final null, truncated large body and <=262144-byte output at 100-item request; next page resumes after actual last emitted ID. Test exact tag/query/enabled, since date/tracker and linked filters including invalid date/type, empty dataset, not-found fixed errors, injected sqlite/upstream exception text masked. Test non-admin gets no `probe` destination object; admin sees only the allowed metadata and never credentials/digests/raw errors/labels. Inspect every tool annotation. Canary assertions include protocol errors, audit records and captured logs.
- [ ] Add table-driven `check_state` tests freezing UTC: disabled wins; retry/cooldown future =>deferred with later applicable boundary; null last checked =>due; elapsed interval =>due; future interval =>scheduled; document due is eligibility, not guaranteed execution if scheduler stopped. Patch every network helper to raise if invoked by cached reads, including releases/inventory summary.
- [ ] Run `python -m unittest discover -s tests -p 'test_mcp_reads.py' -v` (red). Implement explicit SELECT columns and allowlist projections, finite policy checks both list and call, byte bounds before return; use SDK type validation with forbid-extra fallback from Task 1. Add authenticated message counters including discovery. Rerun tests (green).
- [ ] Prepare authorised commit: `git add radar/mcp_tools.py radar/mcp_server.py tests/test_mcp_reads.py && git commit -m "feat: expose bounded role-filtered MCP reads"`.

## Task 5: Controlled operations, audit and worker-owned leases (Phase 1)

**Files:** `radar/mcp_tools.py`, `radar/db.py`, new `tests/test_mcp_operations.py`.

**Interfaces:** exact operational signatures above. Internal `acquire_operation(principal: Principal, tool: str, tracker_id: int | None) -> str` opens immediate transaction, revalidates principal, counters, unique tracker lease, per-key/global caps and writes dispatch audit; returns lease ID. `release_operation(lease_id: str, outcome: str) -> None` outcome audit and deletion in transaction, called in worker thread `finally`. Inventory enqueue and audit use one immediate transaction; no external work under SQLite write lock. No server request-timeout wrapper.

- [ ] Write tests that patch at the actual `mcp_tools` import locations and assert exact calls:

```python
from radar.checker import CheckResult

async def test_check_has_only_declared_side_effects(self):
    result = CheckResult(self.tracker_id, 'Demo', 'example/demo', 'ok', event_id=42, changed=True)
    with patch('radar.mcp_tools.check_tracker', return_value=result) as check, \
         patch('radar.mcp_tools.dispatch_release_notifications') as notify, \
         patch('radar.probes.probe_tracker', side_effect=AssertionError('probe forbidden')), \
         patch('radar.portainer.sync_inventory', side_effect=AssertionError('sync forbidden')):
        await self.call(self.admin_ops_key, 'tracker_check', {'tracker_id': self.tracker_id, 'confirm': True})
    check.assert_called_once_with(self.tracker_id, run_probe=False)
    notify.assert_called_once_with([42])
```

- [ ] Add integration tests using real `check_tracker` with mocked GitHub/AI/notification transports: changed non-baseline creates one event and expected notification counts; baseline/no change no new event; auto-analysis disabled =>no model call, enabled+event =>model call, cooldown =>no GitHub/probe/sync and deferred result; disabled tracker explicitly checkable. Missing/false/string confirm for either check or probe causes no work. Patch `radar.checker.probe_tracker`, `radar.checker.sync_inventory`, `radar.probes.sync_inventory`, `radar.auto_analysis.chat` and notification send functions at their actual lookup sites, not merely original defining modules. Preserve browser/scheduler behaviour. Do not claim auto-analysis is newly deduplicated: checker can recover an existing event ID under a race, an existing limitation to disclose/review rather than silently refactor.
- [ ] Probe test requires configured destination unless inventory mode, calls `probe_tracker(id, refresh_portainer=False)` exactly once; live HTTP/TCP/SSH uses existing constrained validated code, cached inventory never syncs and includes provider sync time. Missing configuration does not acquire outbound side effects. Inventory sync returns existing active job ID, never inline sync; rollback with audit covered by Task 1.
- [ ] Add threaded event/barrier test: block actual operation, disconnect/timeout SDK client, query lease remains, second same-tracker call rejected with retry time, release first, assert outcome audit and lease removal; no need to receive discarded response. Add cross-key same-tracker, per-key/global cap, expired lease reclamation, failure-finally release, injected audit failure fail-closed before dispatch. Rate tests cover each limit exactly at N/N+1 and next window, with browser/scheduler unaffected. Re-auth revocation/demotion between verification and dispatch runs nothing.
- [ ] Calculate outbound worst-case from actual GitHub lookup branches, optional 120-second model call and **number of notification recipients/channels** times existing 15-second send time. A 300-second lease is not safe merely because each send has a timeout. If fan-out can exceed the lease, report a blocking design assumption and obtain approval for the narrow correction (longer provable bound or heartbeat); do not ship an expiring live lease. Do not silently remove notifications/analysis or reduce recipients to satisfy the bound.
- [ ] Run `python -m unittest discover -s tests -p 'test_mcp_operations.py' -v` (red), implement approved counters/lease/audit tables and the exact operation wrappers, then rerun (green), inventory concurrency and full regressions.
- [ ] Prepare authorised commit `git add radar/mcp_tools.py radar/db.py tests/test_mcp_operations.py && git commit -m "feat: constrain and audit MCP operations"`. Stop for independent Phase-1 security review; capture `.dev/reviews/SRR01-4-phase1.json`, run V12A from the contract (Phase-1 report only), fixes rerun relevant and full tests. Require owner acceptance and explicit Phase-2 start authority. V12 checks all three reports at final review only, never blocks Phase 1 waiting for future reports.

## Task 6: Tracker data writes with no implicit outbound work (Phase 2)

**Files:** `radar/mcp_auth.py`, `radar/mcp_tools.py`, `radar/tracker_utils.py`, `radar/web.py`, `tests/test_mcp_writes.py`, Profile scope choices.

**Interfaces:** `TrackerCreate`, `TrackerPatch`, four exact tracker mutation tools above. Use current admin+scope in the same immediate transaction as data and audit; no calls to browser form because it checks immediately. Reuse existing normalisers/validation, not browser request context.

Shared narrow helpers in `tracker_utils.py`: `validate_tracker_core(values: dict[str, object], *, existing: dict[str, object] | None = None) -> dict[str, object]` normalises only supplied core fields and applies existing browser messages; `reset_release_state(conn: sqlite3.Connection, tracker_id: int, *, clear_last_checked: bool) -> None` shares the existing reset SQL. Browser delegates core validation/reset with `clear_last_checked=False`, retains probe validation, repository-change event deletion and immediate check; MCP uses `True` for strategy/prerelease changes. Reuse the existing optional HTTP/HTTPS URL validator by moving its logic to the shared helper, leaving the browser name delegating for unrelated callers. Do not apply new MCP-only note/tag limits to existing browser inputs.

- [ ] Add actual SDK tests: create normalises repository, duplicate =>fixed conflict, invalid URL/name/refresh/tags/type/unknown field rejected, inactive/demoted/read-only key cannot mutate. `tracker_update(...changes={'repository':...})` rejected, no event/history deletion on any allowed update. Probe credentials/configuration fields rejected. Delete `confirm=false` does nothing, true deletes via FK cascade and audit, absent ID fixed error.
- [ ] Use the following regression method with network helpers patched to raise:

```python
async def test_writes_never_check_probe_or_sync(self):
    with patch('radar.checker.check_tracker', side_effect=AssertionError('outbound')), \
         patch('radar.probes.probe_tracker', side_effect=AssertionError('outbound')), \
         patch('radar.portainer.sync_inventory', side_effect=AssertionError('outbound')):
        created = await self.call(self.admin_write_key, 'tracker_create', {'tracker': {'name': 'Demo', 'repository': 'example/demo'}})
        row = self.read_tracker(created['tracker_id'])
        self.assertIsNone(row['last_checked_at'])
        await self.call(self.admin_write_key, 'tracker_update', {'tracker_id': row['id'], 'changes': {'notes': 'reviewed'}})
        self.assertIsNone(self.read_tracker(row['id'])['last_checked_at'])
```

- [ ] Add cases with existing timestamps: ordinary edits preserve scheduling, strategy/prerelease change resets current release fields, last status/error/retry and clears `last_checked_at` without deleting historical events. Toggle enabled preserves timestamps, due/disabled reads correct. Roll back audit and data together on injected audit error. Planted mutation-only key is invalid. Delete reports event/decision counts that match cascaded rows. Existing browser add/edit/source-change/probe field tests pass unchanged and validation messages remain stable.
- [ ] Run `python -m unittest discover -s tests -p 'test_mcp_writes.py' -v` (red), add only approved fields and fixed SQL assignments; extend effective scope allowlist/Profile choices to Phase 2 after gate and configure final server registration as `register_tools(server, phase=2)`. Phase is a code/deployment capability, never a caller-controlled parameter or new environment toggle. Run command (green), auth tests proving Phase-1 capability mode still rejects Phase-2 scopes.
- [ ] Prepare authorised commit: `git add radar/mcp_auth.py radar/mcp_tools.py radar/tracker_utils.py radar/web.py radar/templates/profile.html tests/test_mcp_writes.py && git commit -m "feat: add constrained MCP tracker writes"`.

## Task 7: Atomic upgrade review shared with browser (Phase 2)

**Files:** `radar/db.py`, `radar/upgrade_workflow.py`, `radar/web.py`, `radar/templates/upgrade_decision.html`, `radar/mcp_tools.py`; new `tests/test_upgrade_concurrency.py`, extend browser tests.

**Interfaces:** `save_upgrade_review(tracker_id: int, submitted_release_key: str, expected_revision: int, review: dict[str, object], *, user_id: int, mark_deployed: bool = False, conn: sqlite3.Connection | None = None) -> dict[str, object]`. `ValueError` for public validation/conflicts with fixed text; fresh tracker/decision read under immediate transaction, caller-supplied connection reuse, new row revision 1. Browser owns admin+CSRF; MCP caller owns principal check in same transaction and never supplies mark_deployed. Return exact upgrade projection. Existing validators and `release_key` reused.

- [ ] Write migration test initialises old populated schema twice, revision defaults 0, data/unique constraints retained. Write helper tests current new review revision 1; stale 0 rejected; accepted next expected revision increments; unknown historical key refused; existing historical decision editable but never mark-deployed; moved current release submission without historical decision rejected; deployed row immutable for both save and mark-deployed. Validate decision/priority/risk/date/URL/checklist/notes as interface specifies.
- [ ] Pin race with independent processes (not merely two sequential requests): both start from expected revision 1, one save, one mark-deployed, gate start using multiprocessing Event. Only one succeeds; if save wins, retry browser mark-deployed with fresh revision, then assert deployed row cannot be overwritten by the old save. Assert matching audit/revision and rollback on audit failure. SQL uses `WHERE id=? AND revision=? AND decision_status <> 'deployed'`; inserted-row unique conflict becomes controlled conflict.
- [ ] Browser form round-trip uses hidden `release_key` and `revision`, refuses missing/stale fields with warning; GET current/historical works; CSRF/admin restrictions retained; stale redirect does not overwrite. Update existing browser tests to submit actual hidden fields, not weaken expectations.
- [ ] Actual test core (fixture inserts current release and supplies valid `self.review`):

```python
def test_stale_save_cannot_overwrite_deployed(self):
    first = save_upgrade_review(self.tracker_id, 'v2', 0, self.review, user_id=self.admin_id)
    deployed = save_upgrade_review(self.tracker_id, 'v2', first['revision'], self.review,
                                   user_id=self.admin_id, mark_deployed=True)
    with self.assertRaises(ValueError):
        save_upgrade_review(self.tracker_id, 'v2', first['revision'], self.review, user_id=self.admin_id)
    self.assertEqual(deployed['decision_status'], 'deployed')
```

- [ ] Run `python -m unittest discover -s tests -p 'test_upgrade_concurrency.py' -v` and `python -m unittest discover -s tests -p 'test_mcp_writes.py' -v` (red). Implement additive column/shared helper, browser hidden fields and MCP review tool with both required bindings and transaction audit. Rerun (green), full browser/security suite.
- [ ] Prepare authorised commit `git add radar/db.py radar/upgrade_workflow.py radar/web.py radar/templates/upgrade_decision.html radar/mcp_tools.py tests/test_upgrade_concurrency.py tests/test_mcp_writes.py tests/test_radar.py && git commit -m "fix: bind upgrade reviews to release revisions"`.

## Task 8: SDK integration, clean containers, docs and independent review

**Files:** new `tests/test_mcp_http.py`, `scripts/mcp_acceptance.py`, `scripts/mcp_deploy_verify.py`; docs listed in file map; `.github/workflows/ci.yml`; evidence/review files.

**Interfaces:** `python scripts/mcp_acceptance.py --project srr01-4-acceptance` creates its **own** temporary environment and named Compose project, local-only ports, generated dummy secrets, temporary SSH directory and named data volume; rejects any project other than the explicit acceptance name/prefix, no existing project/production `.env`, no real credentials. It writes a temporary override using absolute repository paths so Compose interpolation uses only its own env file. Runs config/build/up/health/SDK smoke/restart/backup/restore/rollback/profile-disable tests; finally downs/removes **only its own** project/volumes and temporary artifacts. No command output containing secrets/config dump is retained. `python scripts/mcp_deploy_verify.py --record-dir "$RADAR_VERIFY_DIR"` is read-only: checks local Compose container state/image labels, fetches health via operator-provided env `RADAR_PUBLIC_URL`, `RADAR_MCP_URL` and existing operator-held tokens supplied only via protected env, writes sanitised assertions JSON. Does not create keys, invoke writes/operations, change env or fetch/pull/build/deploy. Default missing inputs exit 2, never silently pass/skip required checks.

Acceptance subprocesses pass a generated **environment dictionary**, not secret command-line values. Existing backup/restore scripts inherit `COMPOSE_PROJECT_NAME`, `COMPOSE_FILE` (absolute isolated override/base paths) and all generated interpolation variables, so their internal `docker compose` commands cannot target the default project or load real configuration. Assert resulting project/container/volume labels before any mutating acceptance command; refuse if the acceptance project already exists. The isolated rollback candidate is the baseline `6624d4d2a2f03956a0cfc2397e064f461aaef6a1` image built from `git archive` in a temporary directory, not a branch/worktree or assumed cached image.

Deployment verification requires private `$RADAR_VERIFY_DIR/baseline.json` with `approved_sha,head_before,image_ids_before,backup_integrity,backup_mode,maintenance_authorised,git_workflow_verified,route_verified` populated from actual preflight; each boolean must be true, integrity `ok`, mode `0600`. Script checks current health `commit` and each runtime image label equals `approved_sha`, service states, live SDK read and exact role tool set. Env `RADAR_MCP_URL`, `RADAR_MCP_KEY` and owner-created **already revoked** `RADAR_MCP_REVOKED_KEY` are mandatory for complete production verification. Missing auth must give 401, revoked must give 401, valid scope-filtered session must succeed; script never revokes/creates a credential. Retain sanitised result booleans/revisions only, not baseline private paths/image config/token values. Missing production-specific prerequisites exit 2 and remain blocked.

- [ ] Write `test_mcp_http.py` using `unittest.IsolatedAsyncioTestCase`, SDK `streamable_http_client` and `ClientSession`, real local uvicorn subprocess, temporary SQLite and locally created fixture keys, `trust_env=False`. Initialise, assert protocol negotiation, complete tool set, structuredContent shape, read/call errors, live revocation, demotion, Host/Origin/auth and cancellation. Use imports/signatures confirmed in Task 1, not legacy FastMCP guesses. Test browser Profile creates key, SDK uses it, browser revokes, next SDK request 401. Both documented protocol behaviours run to completion. Fake outbound services only.
- [ ] Run `python -m unittest discover -s tests -p 'test_mcp_http.py' -v` (red), implement scripts and final integration, rerun (green). Unit-test script refusal of unsafe project/missing verify inputs and redaction in `test_mcp_http.py`; do not use a real token in argv.
- [ ] Run ordered local validation: `python -m pip check`; `python -m compileall -q radar scripts tests`; `git diff --check`; `python -m unittest discover -s tests -v`; `python scripts/mcp_acceptance.py --project srr01-4-acceptance`. The acceptance script runs `docker compose ... config`, `build`, clean start without profile (/healthz port 8080, scheduler/worker running, no MCP), with profile (/healthz 8081, real SDK auth call), read/write scope tests, persistence/restart/revocation, backup integrity and isolated restore via existing scripts, then rollback to baseline image against copied upgraded state with additive schema retained, finally MCP-profile removal leaving web/scheduler/worker healthy. Restore is only inside its isolated project; no live database restore.
- [ ] Extend CI with the isolated acceptance command after dependencies and Docker setup, retaining all current Python, security, normal Compose, backup/restore/restart checks. Run `python -m pip_audit -r requirements.txt`; `bandit -r radar -q -ll -f json -o "$RADAR_BANDIT_REPORT"` then `python scripts/check_bandit.py "$RADAR_BANDIT_REPORT"` using privately generated temp report path. Install scanner versions only in the execution/CI environment after authority, using existing CI pins. Capture initial scanner exit and reviewed result, do not hide findings. Secret scan includes changed files and sanitised evidence with locally planted canaries; use the assertion test `python -m unittest discover -s tests -p 'test_mcp_reads.py' -v` plus independent diff/log review, do not label this a universal credential scanner.
- [ ] Document all tools and pagination, scopes/admin exceptions, browser key expiry/invalidation, one-time display, HTTPS/proxy trust, no CORS, retry/disconnect guidance, cached inventory, optional analysis and standard notification effects, supported local/reverse-proxy arrangements, MCP-only limits, additive migrations, worker-stuck-job and duplicate-notification limitations, OAuth-only clients unsupported. Verify example SDK/client configuration uses env-held bearer key, not password/cookie/query or committed secret. No OpenChamber MCP client integration is added.
- [ ] Freeze diff; independent `claudex_reviewer` reviews complete code/tests and first-phase gate, with focus on auth freshness, SDK middleware, ASGI bypass, bound outputs, quotas/leases, audit atomicity, side effects, upgrade races and real Docker behaviour. Required report `.dev/reviews/SRR01-4-security.json` contains `reviewer,independent,verdict,findings` and references exact reviewed Git/diff digest and commands. Codex independently assesses every AC/evidence mapping, no unresolved critical/high findings. Implementer cannot self-attest independence. If reviewers unavailable, stop at review blocker, not substitute self-review. Rerun affected tests, full suite and container acceptance after fixes.
- [ ] Prepare authorised docs/test commit, only explicit files from map, no `git add .`. Obtain specific push/PR authority, open focused PR, require all existing and new CI checks and independent review, then obtain merge authority. This is not public-release authority. Record actual PR, checks and merged SHA when they exist.

## Task 9: Production deployment gate, backup, smoke, rollback and YouTrack

**Files:** docs/MCP.md runbook; `.dev/tasks/SRR01-4.evidence.json`; no committed production files. Owner-requested deployment stays in scope but blocked, not represented as completed by local tests.

**Interfaces:** existing `scripts/backup.sh [stamp] [dest]`, `scripts/restore.sh BACKUP.db --confirm` (live restore needs separate destructive authority); read-only verification script from Task 8. Operator supplies privately `RADAR_DEPLOY_CHECKOUT`, `RADAR_APPROVED_SHA`, `RADAR_VERIFY_DIR`, `RADAR_PUBLIC_URL`, `RADAR_MCP_URL`, existing secure key and confirmed Compose/proxy configuration. These are runtime inputs, not new product configuration or fictional host values.

- [ ] Confirm host/checkout/access route, compose project/volume identity, private env/SSH mounts preserved, current live revision/image IDs and image labels, storage capacity, maintenance window, approved merged SHA and explicit existing proxy route. Confirm no public MCP port, exact trusted peer list, TLS/Host/Origin policy and non-default secrets privately. If key absent, owner provisions through Profile separately; deployment request does not authorise agent credential creation. No DNS/network/proxy modifications. If host checkout differs from public layout, follow existing-installations comparison workflow before mutation; do not replace it blindly.
- [ ] Record baseline and backup privately in the identified existing production checkout, before source/schema change:

```bash
test -n "$RADAR_DEPLOY_CHECKOUT" && test -n "$RADAR_APPROVED_SHA"
cd "$RADAR_DEPLOY_CHECKOUT"
git status --short --branch
git rev-parse HEAD
docker compose ps
docker compose images
bash scripts/backup.sh
```

Retain old image IDs/config and backup path privately; verify script integrity result `ok`, permissions 600 and storage identity. Dirty tracked source, missing backup/route or unexpected containers =>stop. Do not publish private paths/IPs/config/secrets in YouTrack or repository.

- [ ] Only after all authority/CI/review gates, fetch approved source through existing read-only route and assert merge target, without blindly deploying newest main:

```bash
git fetch origin --prune
test "$(git rev-parse origin/main)" = "$RADAR_APPROVED_SHA"
git merge --ff-only "$RADAR_APPROVED_SHA"
export RADAR_BUILD_COMMIT="$RADAR_APPROVED_SHA"
docker compose --profile mcp config --quiet
docker compose --profile mcp build --pull
docker compose --profile mcp up -d --build
python scripts/mcp_deploy_verify.py --record-dir "$RADAR_VERIFY_DIR"
```

Before run, confirm existing deployment env already safely configures MCP. If edits are necessary, seek approval for that exact deployment config diff; this task does not imply proxy or credential changes. No publish-container workflow, tag, release, or GHCR push.

- [ ] Smoke must prove live `/healthz` commit equals approved SHA, web healthy and login/Profile usable, scheduler and inventory worker running, MCP health and actual SDK initialise/list/read with human-provisioned key, missing/revoked key denied and role-filtered tools, no secrets in errors. Revocation smoke uses a separately owner-authorised temporary human-created key; if unavailable mark that production-specific check blocked, not passed. Never run live tracker operations/data writes or send notifications just for smoke without specific test-target authority. Verify existing data counts/representative tracker and upgrade records without private content retention.
- [ ] On failure, stop MCP first (`docker compose stop mcp`), redeploy retained previous images/config through existing operator route, keep additive tables/columns and user data, verify old web health/login and workers. The previous image reference is recorded baseline, never an invented version. Do not `git reset --hard`, delete volumes or drop migrations. If data restoration is needed, stop and obtain explicit restore authority; then existing guarded restore with verified backup and safety backup, followed by health/data verification. Rehearse this path in isolated Task 8 first.
- [ ] Record exact merged/deployed SHA, baseline image/backup integrity (sanitised reference only), validation outputs, security and Codex reviews, AC-by-AC evidence, rollout/smoke and rollback rehearsal in evidence JSON. Run `python3 /Users/muhdusama/.agents/skills/dev-task/scripts/devtask.py validate-evidence .dev/tasks/SRR01-4.json .dev/tasks/SRR01-4.evidence.json`. Required blocked deployment checks remain unverified; never manufacture all-pass evidence to close the issue.
- [ ] Through configured YouTrack identity/capability, verify target `SRR01-4`, then update state, next action/blockers and evidence together at material transitions. Record exact plan/task digest, PR/merged SHA, local and production results and review links, no secrets/private host facts; read back the changed issue. Final human approval binds exact evidence digest; only then final closure workflow. Missing write capability is a recorded blocker, not permission to bypass identity. No issue write is made by this planning call.

## Acceptance-to-validation map (contract is canonical)

- AC1 optional standard authenticated SDK service + unchanged default stack: V1 `test_mcp_sdk.py`, V3 `test_mcp_transport.py`, V8 `test_mcp_http.py`, V10 isolated Compose acceptance.
- AC2 browser-only key lifecycle, strict invalidation and phases: V2 `test_mcp_auth.py`, V8 browser-to-SDK lifecycle.
- AC3 exact allowed tool set and **all** admin exclusions: V4 `test_mcp_reads.py`, V6 `test_mcp_writes.py`, V8 complete tool-set equality (includes absence of settings/users/roles/credentials/keys/SQL/shell/deploy/bulk/import/test-notification/mark-deployed).
- AC4 bounded cached reads, all pagination, safe projections/errors and check-state: V4, V8 canary/network-denial and byte-bound tests.
- AC5 HTTPS/forwarding/Host/Origin/body/rate/concurrency/audit guards: V3, V5 operations tests, V12 independent review.
- AC6 declared check/probe/sync side effects, durable lease and transactional enqueue: V5, V0 multiprocess queue tests, V12 bound/fan-out review. Unsafe lease assumption is an explicit replan blocker, not exempted acceptance.
- AC7 all Phase-2 tracker writes/scheduling/delete confirmation and no outbound effects: V6 writes tests, V9 full regressions.
- AC8 release/revision-bound reviews and browser-only deployment marking: V7 multiprocess concurrency/browser tests, V6 MCP review tests.
- AC9 real SDK client integration, full regressions, clean containers, backup/restart/rollback: V8, V9, V10, V11 scanners.
- AC10 independent Phase-1/final security review and Codex evidence assessor, no open critical/high: V12 review report check, V14 evidence validation. Human review is required in addition to a report-format command.
- AC11 owner-requested gated deployment baseline/backup/commit/health/smoke/rollback: V13 operator-side verification, V10 rehearsal, V14 evidence; blocked until identified target, release-route prerequisites and deployment-config authority. Local verification is not production evidence.
- AC12 YouTrack evidence and exact approval boundaries: V14 evidence validator plus authenticated live read-back of SRR01-4 after authorised update. Do not infer issue completion from a file.

V12A validates Phase-1 report only at its gate; V12 requires Phase-1, final security and Codex reports at the final gate. All runnable validation commands, including the configured `functions.execute` YouTrack read-back (V15, tool success rather than shell exit), are embedded in `.dev/tasks/SRR01-4.json`. A report-format assertion is necessary but never sufficient evidence that independent review or live issue maintenance occurred.

## Plan self-review and handoff

- [x] Full revision-3 design checked: all 18 tools, inventory/job admin restrictions, pagination, bounded responses, redaction, check-state, browser-only credentials, analysis/notification side effects, concurrency, migration and both phases mapped above.
- [x] No product files or executable scripts created by planning. Proposed test imports/methods/interfaces are defined above; fixtures follow existing temporary SQLite/Flask/SDK patterns.
- [x] Deployment request distinguished from identified target/config/credentials and Git release authority. SDK/fan-out assumptions have concrete checks and stop/replan conditions, not fabricated results.
- [x] Execution method unselected; no branch/commit/CI/review/deployment result asserted. Original spec preserved with dated addendum only.
- [ ] Owner reviews exact contract digest and this plan and selects method. Suggested choice: single implementer specialist with coordinator native supervision plus independent security/Codex assessment; no parallel writers. Alternatively native implementer plus the same independent final reviewers.
- [ ] If approved scope/interfaces/baseline/branch change, update bound contract and obtain renewed exact-plan approval before implementation.

Approval request: Does this exact plan capture the approved design and both phases? Approve its displayed digest and choose the execution method. Production target/access/config details and specific branch/commit/push/PR/merge authority remain separate gates.
