# Test audit (2026-11-17)

**Done 2026-11-17: A.1 and B.** B was cut down after measuring: only Armory `tests/math` (280 tests, about 42 s) and Legion `test_private_integration.py` (6 tests, about 11 s) are `slow`. Portcullis `test_backup`/`test_migrations` (104 tests, 28 s) and `test_traffic` (37 tests, 10 s) are fast enough and guard data, so they stay in the default run. Stronghold's zip-bomb tests are security checks and 3 s, so they stay too. `pytest` skips `slow`; `pytest -m ""` runs everything. Results: Armory 126 s to 72 s, Legion 41 s to 20 s. **Done 2026-11-17: C.1 and C.2.** Portcullis full run 12m12s to 9m37s (the run shared the machine with other jobs). Ember vitest 79s to about 12s (`vmThreads`; `turnStream.test.ts` keeps the default pool). Admin apps left as they are (3 to 14 s each). C.3 (xdist) and E are not done.

Nothing is deleted yet. This lists what to remove, what to stop running every time, and what to speed up. Each item needs a yes before it is done.

## Measured (full runs, one machine, run in parallel)

| Suite | Tests | Time |
|---|---|---|
| portcullis (pytest) | 990 | 12m12s |
| armory | 1839 (+1 skipped) | 2m06s |
| stronghold | 711 | 1m21s |
| legion | 1422 | 41s |
| treasury | 52 (+13 skipped) | 4s |
| ember (vitest) | 2213 | 79s |
| admin apps (vitest) | not timed | small |
| portcullis_admin e2e (Playwright) | 21 | needs Chrome |

Portcullis is 70% of all backend time and has no single slow test: the slowest is 4s. Each test starts a whole app (about 1.2s: migrations 0.4s, bootstrap-admin password hash 0.1s, the rest start and stop). Cheaper password hashing alone gave no gain (tried, reverted).

## A. Remove: dead code and its tests

1. **Portcullis `AgentGateway` / `McpAgentGateway`** (`src/services/agent_gateway.py`, 261 lines). Nothing calls it: `get_agent_gateway` has no user and `app.state.agent_gateway` is only set. The turn engine that used it moved to Stronghold in Plan 10. Only the `Caller` class in that file is still used.
   - Delete: the gateway classes, `deps.get_agent_gateway`, the `agent_gateway` argument of `create_app`, `FakeAgent` in `tests/conftest.py`, and `tests/test_agent_gateway.py` (416 lines, includes the 2.5s tests). Move `Caller` to its own small module.
   - Check `tests/test_account_agents.py`, `test_branch.py`, `test_chat_folders.py`, `test_logs.py`, `test_permission_split.py`, `test_traffic.py` for uses of `agent`/`FakeAgent` and trim them.
2. **Shared-token tests**: `test_shared_token.py` exists in five projects and `shared_token.py` in five. They go away when Plan 12 (dynamic service auth) replaces the shared token, so do not touch them before then.

## B. Not run every time (opt-in markers)

Add a `slow` marker; the default run is `-m "not slow"`, a full run is `pytest` with no filter or `-m slow`.

| Tests | Why | Size |
|---|---|---|
| `legion/tests/test_private_integration.py` | real MCP servers started, restarts, 5.7s test | 5 tests, about 11s |
| `armory/tests/math/` (21 files, 188 tests) | real worker processes and pools | about 60s of the 126s |
| `portcullis/tests/test_backup.py`, `test_migrations.py`, `test_traffic.py` (real gateways) | real timers, files, unreachable hosts | about 15s plus fixtures |
| `stronghold/tests/test_extraction_limits.py` (zip bombs) | 0.7s each | 4 tests |
| `treasury/tests/test_backend_contract.py` Postgres and Firestore | already skipped without a DSN or emulator | keep as is |
| Playwright e2e in `portcullis_admin` | needs Chrome, own command | already separate |

Run them before a merge to `main` and in CI; skip them while iterating.

## C. Speed up (no tests removed)

1. **Portcullis app start per test (largest gain).** Build the migrated database once per session and copy the file for each test, instead of migrating each time. Estimate: save about 0.4s of 1.2s per test, so about 5 minutes. Needs a check that no test depends on a fresh migration (`test_migrations.py` keeps its own path).
2. **Vitest jsdom** (ember): jsdom is created 181 times. Vitest's own report says `pool: 'vmThreads'` or `isolate: false` removes most of that. Try it, keep it only if the full run stays green.
3. **pytest-xdist** on Portcullis (the `popen-gw` folders in `.cache` show it was tried). Four workers would take 12 minutes to about 4, if tests do not share ports or files.

## D. Looked at and kept

- Portcullis and Stronghold have test files with the same names (`test_chats`, `test_shares`, `test_notes`, `test_attachments`, and others). They are not duplicates: Portcullis tests login, permission and pass-through; Stronghold tests the logic. Test names overlap in 4 of 11 pairs, 1 or 2 names each.
- `stronghold/tests/test_agent_directory.py` and `test_agent_gateway.py` are exact copies of Portcullis's apart from 4 to 6 lines. Stronghold uses its copy; the Portcullis `agent_directory` is still used by `agent_admin`/`server_info`, so both stay.
- Armory `test_coverage*.py` are real tests of the math tool, not padding.

## E. Disk, not tests

`apps/portcullis/.cache` is 1.6 GB and `apps/portcullis/data` is 352 MB of old test folders (`live-dictation-*`, `architect-parallel-suite`, `.test-capability-*`). They are gitignored. Safe to delete after you say so.

## Suggested order

1. A.1 (dead gateway and its tests).
2. B (markers and the default `-m "not slow"`), with the commands in each README.
3. C.1 and C.2.
4. E.
5. Plan 12 removes A.2.
