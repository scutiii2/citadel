# Plan 13 verification report

Branch: `plan-13-service-catalog`, created from committed main `09cc60c7`.
Worktree: `D:/User/Documents/Programming/Applications/Citadel/.worktrees/plan-13-service-catalog`.
Original checkout's pre-existing changes remain untouched. No push, merge or Brain changes.

## Commands

- **PY**: `uv run pytest -q -p no:cacheprovider`, from the named app/library folder.
- **FAST**: PY plus `-m "not slow"` for Armory and Legion.
- **UI**: `pnpm exec vue-tsc -b` then `pnpm exec vitest run`, from the named admin app.
- Shared auth: `uv run scripts/sync_citadel_auth.py` and `uv run scripts/sync_citadel_auth.py --check`, from repo root.

## Per-task results

| Task | Commit | Change | Observed verification |
|---|---|---|---|
| 1 | 02e35c61 | Shared catalog client, address helpers, transport, cache, exports; synchronized copies | Missing-module RED; focused catalog 21 passed; library PY 71 passed |
| 2 | 42436541 | Treasury registration/pin store and signed routes; new SQLite calls off event loop | Missing-store RED; Treasury PY 80 passed, 13 skipped |
| 3 | 4c5ceb51 | settings.manage proxy routes, refusal/outage mapping, address-free audit entries | Three 404 REDs; PY `tests/test_admin_treasury.py`: 9 passed |
| 4 | 9246a1f6 | Treasury Admin Services table, typed API and navigation | Missing-view RED; Treasury Admin UI: 41 passed, type check passed |
| 5a | e694cd63 | Stronghold bootstrap fields and startup/shutdown registration | Four missing-field/catalog REDs; Stronghold PY 730 passed |
| 5b | e57f68f7 | Portcullis bootstrap and registration; remove db_gateway.url | Two startup REDs; PY `-x -k "config or startup or db_gateway or lifespan"`: 33 passed, 938 deselected |
| 5c | c6775810 | Armory bootstrap/registration, remove editable peer addresses and stale rows | Two bootstrap/settings REDs; Armory FAST: 1524 passed, 1 skipped, 280 deselected |
| 5d | e7317df5 | Legion config bootstrap and lifecycle; remove Treasury address card and backend/proxy routes | Legion four REDs and Portcullis removed-route RED; Legion FAST 1406 passed, 6 deselected; Portcullis `tests/test_agent_admin.py` 16 passed; Legion Admin UI 92 passed, type check passed |
| 6a | 2184cf70 | Stronghold logical peer clients; shared connection-error refresh wake | Wrong-host and missing-wake REDs; Stronghold PY 731 passed; catalog focused 22 passed; sync check passed |
| 6b | 75458300 | Portcullis request-time peer lookup and callable MCP session URLs | Fixed-host RED; PY across startup, server-info, proxy, files, attachments, config, gateway and email: 134 passed |
| 6c | 1b12e54a | Armory resolves Stronghold for each brain operation | Fixed-loopback RED; Armory FAST 1525 passed, 1 skipped, 280 deselected |
| 6d | f680c1a7 | Legion catalog default, saved/CLI precedence, callable reconnect URL and failed-startup recovery | Five REDs; Legion FAST 1411 passed, 6 deselected |
| 7 | ed813d7c | Compose bootstrap/advertisement contract, examples and docs | Missing-bootstrap RED; library PY `tests/test_packaging.py`: 3 passed; Compose config passed without warnings |
| 8 | 5b084058 | ASGI start-order/outage flow tests; repair retry, unpin snapshot and address validation defects | Eleven REDs; focused catalog/flow 35 passed; library PY 86 passed; sync check passed |
| 9 | Final close-out commit (see git log) | Full verification, troubleshooting, IPv6 fallback correction, report; vault skipped | IPv6 RED; final library PY 87 passed; full results below |

Task 6b command: `uv run pytest -q -p no:cacheprovider tests/test_catalog_startup.py tests/test_server_info.py tests/test_mcp_proxy.py tests/test_capability_files.py tests/test_attachments.py tests/test_config_issues.py tests/test_db_gateway_client.py tests/test_email_service.py`.

## Final full verification

| Project | Command | Result |
|---|---|---|
| libs/citadel_auth | PY | 87 passed, 1 warning |
| stronghold | PY | 731 passed, 1 warning |
| treasury | PY | 80 passed, 13 skipped |
| armory | FAST | 1525 passed, 1 skipped, 280 deselected, 4 warnings |
| legion | FAST | 1411 passed, 6 deselected, 2 warnings |
| portcullis | PY, background | 972 passed in 1335.30s (22m 15s) |
| legion_admin | UI | Type check passed; 92 passed |
| treasury_admin | UI | Type check passed; 41 passed |
| portcullis_admin | UI | Type check passed; 205 passed |

After IPv6 fix and auth resync, fresh app integration checks passed: Stronghold startup/peer tests 5; Armory startup/resolver tests 9; Legion startup/peer tests 8; Portcullis startup/dynamic-address tests 3.

Existing warnings concern Starlette/httpx deprecation, unresolved FastMCP lifespan annotation and deprecated WebSocket/MCP APIs. No warning suppression or test weakening added.

Compose: `docker compose config --no-env-resolution --quiet`, with dummy process-only gateway admin passwords, passed without warnings. This avoids reading actual env files or printing secrets. No daemon or live deployment run.

## Changes found during work / rulings

1. Dirty original main checkout: used isolated worktree from committed main, preserving all original edits. Per-task commit authorization includes Task 9 and overrides plan's final wait-for-commit line.
2. Plan FakeKeyring lacks private_key/kid needed by real signing: use in-memory Ed25519 test identity; do not bypass auth.
3. Existing fixtures create disposable env/key files. Automatic review initially blocked them; user explicitly approved disposable fixtures only. Real env, secrets and key files remained untouched.
4. Treasury Admin guard picks first allowed nav page: append Services to preserve Instances home. Tests live beside views; router/index.ts also needs its route.
5. Tests of removed settings migrated to remaining public contracts, retaining validation and permission assertions. Portcullis fixtures seed catalog entries instead of removed constructor setting.
6. Armory main had no stale-row cleanup described by plan: delete only obsolete address rows on read. Treasury instance/connection controls keep their group. Create shared catalog module during startup task and reuse it later.
7. Legion registration previously used unmanaged daemon thread: tie catalog/instance tasks to existing ASGI lifespan and cancel on shutdown.
8. Shared CatalogTransport wakes refresh on connection failure for both Stronghold→Portcullis and Portcullis→Stronghold; Armory resolver wakes directly.
9. Legion had no built-in main server. Supply catalog default when missing; saved HTTP URL and stdio config win, CLI remains explicit. Persistent sessions keep their URL until reconnect; callable URL resolves then. Failed startup sessions retry on later tool requests.
10. Extra removed-address reference found in Obsidian capability README and corrected.
11. Planned FastAPI stub required new library dev dependency (same minimum as Treasury). Tests exposed exhausted registration retries, stale pin retention after successful empty catalog snapshots, and malformed base URL acceptance; corrected after observing failures.
12. Final reviewer found IPv6 fallback without brackets killed catalog task. Regraded functional issue and fixed after failing regression; library suite and auth sync rerun. No deferred review findings.
13. Portcullis Admin imports Ember Web source. Install Ember Web locked dependencies to resolve existing Vue imports in isolated worktree; no source/lockfile change there.

Independent review found own-name registration and Portcullis-only pin controls enforced; no security blockers. Review's set-aside items remain explicit scope decisions: existing sessions until reconnect, external service settings unchanged, unavailable live integrations reported, Brain excluded by user.

## Not verified

- Live Docker deployment/container start order.
- Real Postgres integration (13 Treasury skips include unavailable integration backends).
- Real browser rendering/interaction of Services page.
- Simultaneous Windows restart of all services.
- Armory/Legion tests marked slow, intentionally excluded.
- Vault edits/validator, intentionally skipped at user's request.

## Brain notes needing update (not touched)

- Projects/Citadel.md: Architecture and 2026-11-18 Key decisions row.
- Projects/treasury.md
- Projects/treasury_admin.md
- Projects/legion_admin.md (Treasury card removed)
- Projects/armory.md
- Projects/stronghold.md
- Projects/portcullis.md
- Projects/garrison.md
- Decision - JSON configs are tracked and secrets live in .env.md
