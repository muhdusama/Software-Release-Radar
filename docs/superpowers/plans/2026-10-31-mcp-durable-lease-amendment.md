# MCP durable lease safety amendment

## Authority and scope

The owner selected **Durable leases (Recommended)** after Task 5 established that unbounded notification fan-out can outlive the proposed 300-second lease. This written amendment is pending exact-plan approval. It changes only MCP operation ownership and crash recovery; all other approved revision-3 design, tool, authentication, validation, phase-review and deployment boundaries remain unchanged.

Read with `docs/superpowers/specs/2026-10-31-built-in-mcp-design.md` and `docs/superpowers/plans/2026-10-31-built-in-mcp.md`. Where either document prescribes lease expiry, retry timestamps based on expiry, expired-lease reclamation, a finite duration proof, or a heartbeat alternative, this amendment replaces that prescription. Existing API-key expiry, authentication windows and rate-counter expiry are unchanged.

## Exact replacement

- `mcp_operation_leases` contains `id TEXT PRIMARY KEY`, `key_id TEXT NOT NULL`, `user_id INTEGER NOT NULL`, `tool TEXT NOT NULL`, `tracker_id INTEGER`, `created_at TEXT NOT NULL`. Keep the key index and a unique non-null tracker index across check/probe. Do not add `expires_at` or heartbeat machinery.
- Acquire in `BEGIN IMMEDIATE`: re-read authority, apply operation counters, count **all** outstanding leases for global/per-key limits, enforce tracker uniqueness, insert lease and dispatch audit atomically. No age-based deletion or ignored old row. Acquisition failure runs no external work.
- The SDK worker thread owns the lease through the entire operation and outcome audit, including notification/analysis fan-out and client disconnect. Release and outcome audit remain one transaction. If that transaction fails, retain the lease and fail closed; do not delete in a second unaudited fallback.
- No timeout or response end releases work. No server startup, API-key revocation/deletion, password change, user deletion, elapsed clock or ordinary retry clears a lease. In particular, lease rows must not cascade away with users/keys.
- Busy errors say **Operation already running or awaiting operator recovery. Inspect current tracker state before retrying.** Do not invent a completion time or automatic retry timestamp.
- Remove the obsolete `MCP_OPERATION_LEASE_SECONDS` setting from MCP configuration parsing, `.env.example`, Compose service environment, docs and tests. It no longer affects safety or behaviour; an old deployment environment containing it is harmlessly ignored. Other operator knobs and browser/scheduler behaviour remain unchanged.

## Offline crash recovery

Add `scripts/mcp_recover_leases.py` as a local operator-only utility, never an MCP tool, browser endpoint or automatic startup action. It uses the existing database path/connection and transactional audit, not a new service or credentials.

```sh
python scripts/mcp_recover_leases.py
python scripts/mcp_recover_leases.py --confirm-workers-stopped
```

- Without the flag, perform no mutation and exit nonzero with fixed guidance.
- The flag is the operator's assertion, **not** automatic proof, that every MCP worker using this database has stopped and cannot still perform work. The utility cannot prove this across containers/hosts; state this prominently before the runbook command. It must not be executed against a live worker.
- In one immediate transaction, count all lease rows, append an `mcp_operation_recovery` audit record with only the count and fixed statement that prior outcomes are unknown, then delete those rows. Audit failure rolls everything back. Print only the count and fixed recovery summary, not key/user/destination details.
- Deployment runbook: stop all MCP instances sharing the database, verify they have exited using the actual deployment's container/process inventory, inspect tracker/check/probe state and dispatch/outcome audit, execute the explicitly confirmed recovery utility in a one-off process without starting the MCP server, then restart MCP and re-read tracker state before retrying. Recovery cannot undo or establish exactly-once external effects.
- Production recovery is a separate consequential action requiring explicit authority for the concrete target. No live recovery is authorised by this amendment or by the feature's deployment request alone.

## Implementation and validation changes

Task 5 remains the next native task, BASE `1a30db7312b749b207d5ec50f5341e604a1591dc`.

1. Extend `tests/test_mcp_operations.py` first: arbitrarily old lease blocks same-tracker/across-key and applicable per-key/global concurrency; advancing the clock never reclaims it; a client disconnect retains ownership until the worker finishes; success/failure releases only after transactional outcome audit; failed audit leaves ownership intact; revoked/deleted owner does not free an in-flight lease; normal restart does not clear stale rows.
2. Test the recovery utility first: missing flag does not mutate; confirmed recovery clears only lease state and preserves operation-rate counters, jobs, trackers and keys; audit and deletion are atomic; audit failure leaves every lease intact; output has no sensitive fields. Use temporary SQLite databases and subprocesses only, never production recovery.
3. Implement durable ownership in `radar/mcp_tools.py`, additive lease schema/indexes in `radar/db.py`, the recovery utility and configuration removals. Keep all original Task-5 side-effect, literal confirmation, fresh permission, rate-limit, multiprocess enqueue and failure tests.
4. Update `radar/mcp_server.py`, `docker-compose.yml`, `.env.example`, `docs/MCP.md`, and transport tests only for removal of the obsolete setting and documented manual recovery. Do not modify unrelated transport/security behaviour.
5. Run `.venv/bin/python -m unittest discover -s tests -p 'test_mcp_operations.py' -v`, inventory concurrency tests, transport tests, full `.venv/bin/python -m unittest discover -s tests -v`, compileall and `git diff --check`. Verify isolated Compose configuration with profile off/on.
6. Independent Phase-1 security review must explicitly assess no timed reuse, no key/user cascade, disconnect/failure ownership, audit fail-closed behaviour and the limits of the operator assertion. Owner accepts Phase-1 review and explicitly starts Phase 2 as before.

The later isolated acceptance script must rehearse retained stale leases across restart and explicitly confirmed offline recovery against an isolated database. Remove any old test expecting expired operation leases to be reclaimed automatically. No change to notification recipients, outbound timeouts, auto-analysis, browser/scheduler concurrency, or existing inventory-job recovery is authorised.

## Rollback and trade-off

Disabling the optional MCP profile stops new MCP calls. Keep additive schema and audit; do not delete leases as part of rollback or recover a live operation. A crashed operation can block its tracker, key and global capacity indefinitely until verified offline recovery. This is the deliberate availability cost of avoiding overlapping external effects without an unprovable time bound.
