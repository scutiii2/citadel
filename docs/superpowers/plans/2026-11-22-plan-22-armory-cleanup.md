# Plan 22: Armory cleanup (memory, notes, skills, connections, extensions proxy, short-lived downloads) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Armory stops holding anything that Stronghold, Legion or the Brain now own, and its files and downloads live one hour with the time left shown in Ember.

**Architecture:** This is a removal plan, like Plan 20j. Each task first removes the callers of a thing, then the thing, then proves with a test that it is gone and with the suites that nothing else broke. No data is migrated or pruned by a script: the old data stays on disk, unused. The Obsidian chain (Armory `obsidian` and `vault` capabilities, the Brain admin page, Stronghold `/brains`, Portcullis `/api/brains`, Ember Brains page, chat `save_to_second_brain`) is **not** in this plan; it is Plan 22b, because it spans five apps and the chat model. Armory keeps `obsidian` and `vault` until 22b.

**Tech Stack:** Python 3.11+ FastAPI and FastMCP (Armory, Stronghold, Portcullis), Vue 3 + TypeScript + Vitest (Armory Admin, Ember), `uv`, `pnpm`.

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md), sections "Armory" and "Changes from today". Audit: [2026-11-20-scope-audit.md](2026-11-20-scope-audit.md). Roadmap row 22: [2026-11-20-scope-roadmap.md](2026-11-20-scope-roadmap.md). Earlier plans whose leftovers this one removes: 20j, 21.

## Global Constraints

- Remove only what a task names. If a grep finds a live caller the plan did not name, stop that item, record it under "Changes found during work", and keep the code.
- Keep in Armory: `server_manager`, `generator`, `web_research`, `media_downloader`, `firecrawl`, `repo_reader`, `tables`, `math`, `email`, `pdf_merger`, the Docker socket mount (server manager needs it), `obsidian` and `vault` (Plan 22b), Armory's own `settings.db` pages (Capabilities, Settings, Email, Limits).
- Keep in Stronghold: `DELETE /notes/accounts/{uid}`, `src/notes/store.py` and the `notes` catalog entry, because Obsidian publishing still uses them until 22b.
- No data migration, no prune script. Old SQLite files (`memory.db`, `skills.db`, `tickets.db`) and the `connections` table stay on disk.
- Armory never calls Stronghold for anything but what 22b still needs (`/brains/resolve`, `/brains/instance-migration`, `/notes`). After this plan the allowed list for Armory shrinks to those.
- `libs/citadel_auth` is edited only in `libs/citadel_auth/`, then `python scripts/sync_citadel_auth.py` copies it into each app. Never edit a copied `src/citadel_auth/`.
- Downloads live **1 hour** (spec). Do not raise the 5 MB per file and 50 MB total caps in this plan; Task 4 measures media and reports.
- Use `uv` for Python, `pnpm` for Node. Add no dependency. Never read, print or write `.env*`, `secrets/` or key files.
- Keep each file's line endings. One commit per task, each ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Do not push.

## Baseline (record before the first edit)

Run once in a branch `plan-22-armory-cleanup` cut from `main` (Plans 20j, 21, 23 and 24 are on `main`; if not, stop and report). In a worktree whose `.venv` folders are empty, run Python with the main checkout's `.venv\Scripts\python.exe -u -m pytest -q -p no:cacheprovider` from the worktree app folder.

| App | Command | Expected at `ba29fde1` |
|---|---|---|
| Armory | `uv run --no-sync python -u -m pytest -q -p no:cacheprovider` | about 1,409 passed |
| Stronghold | same | about 1,078 passed |
| Portcullis | same (about 13 minutes) | about 1,175 passed, 2 known failures (`test_secret_box.py::test_an_invalid_key_in_env_stops_startup`, `test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`) |
| Legion | same | about 1,489 passed |
| armory_admin, ember | `pnpm exec vue-tsc -b` and `pnpm test` | record the real counts |

Write the real counts under "Baseline results" at the end of this file.

## Assumptions to check (record each result under "Changes found during work")

- **(a)** No agent file under `apps/legion/agents/` or `apps/legion/src/agents/` allows `armory__tool_mem_*`, `armory__tool_notes_*` or `armory__tool_skill_*`. Check: `git grep -n -E "tool_(mem|notes|skill)" -- apps/legion apps/stronghold apps/portcullis apps/ember ':!*.md'`. Plan 20c and 21 should have moved them; any hit is a leftover to fix in Task 1.
- **(b)** Armory's `notes` capability reads Treasury's `notes` collection through `DB_GATEWAY_INSTANCE: armory` and `DB_GATEWAY_CONNECTION: stronghold` (compose). After Task 1 nothing else in Armory uses that connection except Obsidian publishing's Stronghold calls. Check `git grep -n "DB_GATEWAY" -- apps/armory`.
- **(c)** Stronghold's `src/memory/` is only the purge client and route (Plan 20j cut it down). Armory's `memory/routes.py` serves `DELETE /memory/accounts/{uid}`. Check both before deleting.
- **(d)** Armory `skills/routes.py` has no caller left: Stronghold `/skills` is the Brain's own (Plan 20c). Check `git grep -n -E "armory.*/skills|/skills/accounts" -- apps ':!*.md'`.
- **(e)** Stronghold dictation (`src/tool_services/dictation.py`) and attachments call Scribe and Reader themselves; nothing calls Armory's `connection_routes.py` or `services/dictation.py`. Check `git grep -n -E "/connections|/dictat" -- apps/stronghold/src apps/portcullis/src apps/ember/src ':!*.md'`. Hits that are Stronghold's own routes are fine.
- **(f)** Portcullis `src/routes/user_extensions.py` does not call Armory's extension routes (private extensions go to Legion per turn). If it does, keep the Armory piece it needs and record it.
- **(g)** The `[[DOWNLOAD ...]]` marker built by `services/downloads.py` can carry an expiry, and Ember's chat download card parses it (`git grep -n "DOWNLOAD" -- apps/ember/src apps/armory/src`).
- **(h)** Armory's `service_catalog.py` (22 lines) is only how Armory registers itself in Treasury. Keep it if `run.py` registers through it.

## File map

| Area | Remove | Change |
|---|---|---|
| Armory | `src/capabilities/memory/`, `notes/`, `skills/`; `src/connection_admin.py`, `connection_routes.py`, `extension_routes.py`; `src/services/connections.py`, `extensions.py`, `dictation.py` | `src/run.py`, `src/config.py`, `src/services/app_config.py`, `src/services/capability_base.py`, `src/services/downloads.py`, `src/services/session_file_store.py`, `src/citadel_auth/policy.py` (generated), README files, tests |
| Stronghold | `src/memory/` | `src/api.py` (drop the memory router), `src/schema/catalog.py` (drop `memory` if present), README, tests |
| Portcullis | the delete-account `memory` purge entry, the `/api/admin/connections` proxy routes | `src/routes/admin.py`, `src/routes/connections.py`, README, tests |
| Legion | nothing | agent files only if assumption (a) finds a leftover |
| `libs/citadel_auth` | the Armory-to-Stronghold paths `/memory`, `/skills`, `/tickets` | `libs/citadel_auth/.../policy.py`, then sync |
| armory_admin | Connections page, `api/ConnectionsClient.ts`, the Brain page stays until 22b | `src/router/pages.ts`, `src/router/index.ts`, tests |
| Ember | nothing | download card: show time left |

---

### Task 1: Remove Armory memory, notes and skills

**Files:**
- Delete: `apps/armory/src/capabilities/memory/`, `notes/`, `skills/`; `apps/stronghold/src/memory/`; their tests (`git grep -l -E "capabilities.(memory|notes|skills)|tool_(mem|notes|skill)" -- apps/armory/tests apps/stronghold/tests apps/portcullis/tests`).
- Modify: `apps/armory/src/config.py`, `apps/armory/src/services/capability_base.py`, `apps/armory/src/services/app_config.py` (only references to the three capabilities and their settings), `apps/armory/src/run.py` (routes mounted for memory and skills), `apps/stronghold/src/api.py`, `apps/stronghold/src/schema/catalog.py`, `apps/portcullis/src/routes/admin.py`, compose file only if assumption (b) shows `DB_GATEWAY_*` is now unused.
- Test: `apps/armory/tests/test_capabilities_removed.py` (create), plus the existing Stronghold and Portcullis purge tests.

**Interfaces:**
- Consumes: Plan 20c and 21 (Brain skills and tickets live in Stronghold), Plan 20j (Stronghold `memory/` is a purge client and route only).
- Produces: Armory exposes no `tool_mem_*`, `tool_notes_*`, `tool_skill_*`. The delete-account flow in Portcullis no longer calls a memory purge.

- [ ] **Step 1: Check assumptions (a), (b), (c), (d).** Run the greps named above. Record each result. A live caller you did not expect stops the matching removal.

- [ ] **Step 2: Write the failing test**

```python
# apps/armory/tests/test_capabilities_removed.py
import importlib.util

import pytest


@pytest.mark.parametrize("name", ["memory", "notes", "skills"])
def test_removed_capability_cannot_be_imported(name):
    assert importlib.util.find_spec(f"src.capabilities.{name}") is None
```

Also extend the existing test that lists Armory's registered tool names (find it with `git grep -l "tool_generator" -- apps/armory/tests`): assert that no registered name starts with `tool_mem_`, `tool_notes_` or `tool_skill`.

- [ ] **Step 3: Run it.** `uv run --no-sync python -u -m pytest tests/test_capabilities_removed.py -q -p no:cacheprovider` from `apps/armory`. Expected: 3 failures ("is not None").

- [ ] **Step 4: Remove the callers, then the code.**
  1. Portcullis: remove the memory purge call from the delete-account list in `src/routes/admin.py` and its audit action name, and the matching test lines. Keep the notes purge call.
  2. Stronghold: delete `src/memory/`, remove its router include and the `memory` entry in `src/schema/catalog.py` if present, delete its tests. Update `README.md` (drop `DELETE /memory/accounts/{uid}` from the route table).
  3. Armory: delete the three capability folders; remove references in `config.py`, `capability_base.py`, `app_config.py`, `run.py` (a capability's routes were mounted by `run.py`; remove only those three). Delete their tests.
  4. Assumption (a) leftovers: fix any agent file or instruction that still names these tools. The Data Analyst agent's old `skipped_lines` instruction (left by Plan 21) is removed here too: `git grep -n skipped_lines -- apps/legion`.
  5. Compose: remove `DB_GATEWAY_INSTANCE: armory` and `DB_GATEWAY_CONNECTION: stronghold` from the `armory` service only if assumption (b) shows nothing else reads them.

- [ ] **Step 5: Run the suites.** Armory, Stronghold, Portcullis (the purge tests must pass: notes purge stays, memory purge gone), Legion if an agent file changed. Record counts against the baseline.

- [ ] **Step 6: Commit.** `git commit -m "refactor(armory): remove the memory, notes and skills capabilities"`

---

### Task 2: Remove Armory connections, extensions proxy and dictation

**Files:**
- Delete: `apps/armory/src/connection_admin.py`, `connection_routes.py`, `extension_routes.py`; `src/services/connections.py`, `extensions.py`, `dictation.py`; tests that exercise them (`git grep -l -E "connection_admin|connection_routes|extension_routes|services.connections|services.extensions|services.dictation" -- apps/armory/tests`).
- Modify: `apps/armory/src/run.py` (stop mounting them), `apps/armory/src/services/app_config.py` (the connection and extension settings), `apps/armory/src/_fixtures/__init__.py` (fixtures for removed pieces), `apps/portcullis/src/routes/connections.py` (remove the `/admin/connections...` routes that forward to Armory; keep `GET /api/connection-status`, which Stronghold serves), Portcullis tests, `apps/armory_admin/src/router/pages.ts`, `src/router/index.ts`, delete `src/views/ConnectionsView.vue` and its test, `src/api/ConnectionsClient.ts`, update `src/router/guard.test.ts`, READMEs.
- Test: `apps/armory/tests/test_capabilities_removed.py` (extend), `apps/portcullis/tests/test_connections.py` (adjust), `apps/armory_admin/src/router/pages.test.ts` or the existing nav test.

**Interfaces:**
- Consumes: Plan 18 (Legion holds MCP connections), Plan 19 (Stronghold holds Bard, Scribe, Reader connections, dictation and `/tool-services/status`).
- Produces: Armory has no connection records, no REST façade, no extension proxy, no dictation. Portcullis has no route to them. Armory Admin has no Connections page.

- [ ] **Step 1: Check assumptions (e), (f), (h).** Record results. Keep `service_catalog.py` and the registration in `run.py` if (h) holds.

- [ ] **Step 2: Write the failing tests**

```python
# append to apps/armory/tests/test_capabilities_removed.py
@pytest.mark.parametrize("module", [
    "src.connection_admin", "src.connection_routes", "src.extension_routes",
    "src.services.connections", "src.services.extensions", "src.services.dictation",
])
def test_removed_module_cannot_be_imported(module):
    assert importlib.util.find_spec(module) is None
```

Portcullis: in the connections test file add

```python
def test_admin_connections_routes_are_gone(client_with_manager):
    # use the fixture that signs in an account holding extensions.manage; find it in the file
    for path in ("/api/admin/connections", "/api/admin/connections/test"):
        assert client_with_manager.get(path).status_code in (404, 405)
```

If the file uses a different fixture name, use that one and keep the assertion.

armory_admin: the nav test that lists `ARMORY_PAGES` must expect `Capabilities, Brain, Ticket settings, Settings, ...` without `Connections` (read the current list from `src/router/pages.ts` first; remove only `/connections`). The "Ticket settings" page stays: Plan 21 moved tickets, but the page edits Armory's remaining hourly cap setting only if Plan 21 kept it; check `git grep -n "tickets" -- apps/armory/src apps/armory_admin/src` and record what the page still reaches. If it reaches nothing, remove it too and say so in the commit body.

- [ ] **Step 3: Run them; see them fail.**

- [ ] **Step 4: Remove callers first, then code.** Order: armory_admin page and client, Portcullis forwarding routes, Armory modules and their mounting, settings keys, fixtures, README sections.

- [ ] **Step 5: Run the suites.** Armory, Portcullis, `armory_admin` (`pnpm exec vue-tsc -b`, `pnpm test`), Stronghold (its `tool_services/client.py` docstring mentions Armory's old file; reword it only).

- [ ] **Step 6: Commit.** `git commit -m "refactor(armory): remove connections, the extensions proxy and dictation"`

---

### Task 3: Shrink what Armory may call and what may call it

**Files:**
- Modify: `libs/citadel_auth/` policy table (find with `git grep -n "/brains/resolve" -- libs`), then run `python scripts/sync_citadel_auth.py`; the generated `apps/*/src/citadel_auth/policy.py` copies change only through the sync.
- Test: the library's own policy test under `libs/citadel_auth/tests/`, plus each app's auth sync check (`python scripts/sync_citadel_auth.py --check` if the script has one; otherwise run it and `git diff --stat`).

**Interfaces:**
- Consumes: Tasks 1 and 2 (no Armory memory, skills, tickets, connections remain).
- Produces: the policy lets Armory call Stronghold only for `/brains/resolve`, `/brains/instance-migration` and `/notes` (Plan 22b removes these). `/memory`, `/skills`, `/tickets` are gone from the Armory-to-Stronghold list. Prefixes that only Portcullis used for the removed Portcullis proxies stay out of scope unless a grep shows them unused.

- [ ] **Step 1: Write the failing test** in the library's policy test: Armory calling Stronghold `/memory/x`, `/skills/x`, `/tickets/x` is refused; `/notes/x`, `/brains/resolve` and `/brains/instance-migration` are allowed. Use the test file's existing helper for "may this service call this path".

- [ ] **Step 2: Run it; see it fail.** `uv run --no-sync python -u -m pytest -q -p no:cacheprovider` from `libs/citadel_auth`.

- [ ] **Step 3: Edit the policy in `libs/`, run the sync, run the test.**

- [ ] **Step 4: Run Armory, Stronghold, Portcullis and Legion suites** (the copies changed in all four) and `git diff --check`.

- [ ] **Step 5: Commit.** `git commit -m "refactor(auth): Armory may no longer call Stronghold memory, skills or tickets"`

---

### Task 4: One-hour downloads with the time left shown

**Files:**
- Modify: `apps/armory/src/services/downloads.py` (`TTL_SECONDS = 600` becomes `3600`; the marker carries the expiry), `apps/armory/src/services/session_file_store.py` and the place that builds it with `file_ttl_seconds = 6 * 3600` (find with `git grep -n "file_ttl_seconds" -- apps/armory/src`) set to `3600`, the Armory settings page value if it is editable (`git grep -n "file_ttl" -- apps/armory_admin/src apps/armory/src/services/app_config.py`), Ember's download card (find with the grep from assumption (g)), `apps/armory/docs/` and README wording.
- Test: `apps/armory/tests/test_downloads.py` (find the existing file), the Ember download card test.

**Interfaces:**
- Consumes: assumption (g): how the marker is parsed.
- Produces: `Download.expires_at` is `now + 3600` seconds; the marker string has an `expires=<unix seconds>` field; Ember shows "Expires in N min" and, after the time passes, "Expired".

- [ ] **Step 1: Check assumption (g).** Read the marker builder in `downloads.py` and the Ember parser. If the marker already has an expiry field, reuse its name instead of `expires`, and record that.

- [ ] **Step 2: Write the failing Armory tests**

```python
def test_a_download_lives_one_hour():
    from src.services import downloads
    assert downloads.TTL_SECONDS == 3600


def test_the_marker_names_the_expiry(registry_with_clock):
    # registry_with_clock: the fixture the existing tests use to fix time; find it in the file
    marker = registry_with_clock.offer(owner="acct", filename="a.pdf", data=b"x")
    assert "expires=" in marker
```

If `offer` has a different signature, copy the call from an existing test in the file.

- [ ] **Step 3: Write the failing Ember test** in the download card's test file: given a marker whose expiry is 25 minutes from the mocked "now", the card text contains `25 min`; given an expiry in the past, it contains `Expired` and the download button is disabled. Use Vitest fake timers (`vi.useFakeTimers`, `vi.setSystemTime`).

- [ ] **Step 4: Run all three; see them fail for the stated reasons.**

- [ ] **Step 5: Implement.** Armory: TTL constants, marker field. Session files: one hour. Ember: parse the field, show time left, refresh the label every 30 seconds with a timer that is cleared on unmount, disable the button after expiry.

- [ ] **Step 6: Measure.** The spec says the 5 MB and 50 MB caps are revisited at build time. Report, do not change: list the sizes of a typical `media_downloader` result and a typical merged PDF from the Armory tests or fixtures, and say whether media exceeds the 5 MB per file cap. Put the finding under "Changes found during work" for the user to decide.

- [ ] **Step 7: Run Armory and Ember suites, `vue-tsc -b`, `vite build` for Ember.**

- [ ] **Step 8: Commit.** `git commit -m "feat(armory): downloads live one hour and Ember shows the time left"`

---

### Task 5: Docs, sweep and report

**Files:**
- Modify: `apps/armory/README.md`, `apps/armory/src/README.md`, `apps/armory/src/capabilities/README.md` (drop the memory and notes bullets), `apps/armory/docs/`, `apps/stronghold/README.md`, `apps/portcullis/README.md`, `apps/armory_admin/README.md` if it lists Connections, the roadmap row 22 (link this plan, "Armory cleanup built; Obsidian chain is 22b").
- Add: roadmap row `22b` (see below).

- [ ] **Step 1: Sweep.** `git grep -n -i -E "tool_mem_|tool_notes_|tool_skill|extensions proxy|armory.*connections|/memory/accounts" -- apps docs ':!docs/superpowers/plans' ':!*/node_modules/*' ':!*/.venv/*'`. Update only statements this plan made false; list each remaining mention that belongs to Plan 22b.

- [ ] **Step 2: Add the roadmap row** after 22:

```
| 22b | Obsidian chain removal: Armory `obsidian` and `vault` capabilities and Brain admin page, Stronghold `/brains` (personal connections, publishing, promotions, instance migration, `/notes` purge and the legacy notes store), Portcullis `/api/brains` and `/api/admin/brain`, Ember Brains page, chat `save_to_second_brain` fields | 22 | Plan 15 |
```

- [ ] **Step 3: Run every suite once more** and write the final counts under "Final results".

- [ ] **Step 4: Commit.** `git commit -m "docs: Armory cleanup (Plan 22) in READMEs and the roadmap"`

## Self-review

- **Spec coverage ("Changes from today", Armory line):** memory, notes, skills (Task 1); tickets and usage (Plan 21, leftovers in Task 3); connections and extensions proxy (Task 2); short-lived downloads (Task 4); Obsidian and Brain admin page (moved to Plan 22b, stated at the top and in the roadmap). Email delivery audit (spec: "move to Stronghold or drop (open)") is **not** decided here; it stays in Armory and is listed as an open question below.
- **Placeholders:** the places that say "find it with `git grep`" point to code this plan could not name without a long survey; each gives the exact grep. The executor records what it found.
- **Names:** `TTL_SECONDS`, `Download.expires_at`, `registry.offer`, `ARMORY_PAGES` match the code seen on `main` at `ba29fde1`.

## Open questions for the user

1. Email delivery audit table in Armory (metadata only): move to Stronghold or drop? Left in place.
2. The 5 MB and 50 MB download caps against real media sizes (Task 4, Step 6 reports).
3. Armory Admin "Ticket settings" page: removed only if it reaches nothing after Plan 21 (Task 2).

## Manual checklist (pending after the build)

- [ ] Start the stack. In Armory Admin, confirm there is no Connections page and Capabilities lists no memory, notes or skills.
- [ ] Ask an agent to use `tool_mem_search`: it must not exist. Ask it to save and recall a Brain note: it must still work.
- [ ] Delete a test account that has a note: the notes purge runs, no memory purge error appears.
- [ ] Make a PDF merge in Ember: the download card shows "Expires in 60 min" (or close) and later "Expired".
- [ ] Use Bard or Scribe dictation in Ember: still works through Stronghold.

## Baseline results

Branch `plan-22-armory-cleanup` in `.worktrees/plan-22-armory-cleanup`, cut from `main` at `ba29fde1` (Plans 20j, 21, 23, 24 confirmed merged). Python run with the main checkout's `.venv`.

| App | Result |
|---|---|
| Armory | 1409 passed, 1 skipped, 280 deselected |
| Stronghold | 1078 passed |
| Portcullis | 1175 passed, 2 known failures (`test_secret_box.py::test_an_invalid_key_in_env_stops_startup`, `test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`) |
| Legion | 1489 passed, 6 deselected |
| ember | `vue-tsc -b` clean, 203 files, 2394 tests passed |
| armory_admin | not run (nothing in it was changed in the end) |

## Changes found during work

- **(a)** `apps/legion/agents/reviewer.json` still denied `tool_mem_*` and `tool_skill_*` (Armory names). Removed (`"tools": {}`); the two reviewer tests that read Armory's deleted `tool.py` files now use literal names. Stronghold's own `stronghold__tool_skill_*` tools stay. The Data Analyst `skipped_lines` instruction was removed.
- **(b) does not hold.** `apps/armory/src/run.py` registers Armory in Treasury with `DB_GATEWAY_INSTANCE` and `DB_GATEWAY_CONNECTION`. Compose and `config.py` keep them; only the comments changed.
- **(c)** held: Stronghold `src/memory/` was only the purge client and route. `src/schema/catalog.py` had no `memory` entry. `test_catalog_peers.py` used the memory purge as its way to hit Armory; it now uses `DELETE /brains/accounts/u-1`. Portcullis `test_memory_purge.py` became `test_account_purge_forwarding.py` and checks the notes purge (the generic best-effort, redirect and log-redaction cases stay covered).
- **(d)** held: nothing called Armory `/skills` except the policy table.
- **(e)** held: dictation and attachments go Portcullis to Stronghold.
- **(f)** `user_extensions.py` does not call Armory. **But Portcullis `/api/extensions` (GET, POST, DELETE in `routes/server_info.py`, via `McpServerInfo`) forwards to Armory `extension_routes.py`, and Ember's Capabilities page lists extensions through it.** Armory also stores extensions as records in `ConnectionStore` (`services/connections.py`), and `app_config.py`, `run.py` and `_fixtures` depend on that. Decision (user): keep the extension proxy, `services/connections.py`, `connection_admin.py`, the Portcullis `/api/admin/connections` routes and the Armory Admin Connections page. Removed only what nothing calls: `connection_routes.py` (REST façade, its four request helpers moved into `connection_admin.py`), `services/dictation.py`, the WebSocket auth path and sizing, and their tests.
- **(g)** the marker had no expiry field. Added `expires="<unix seconds>"`; Ember's parser reads it as the optional `expiresAt`.
- **(h)** held: `service_catalog.py` stays (`run.py` and the Obsidian code use it), and `require_internal_origin` stays because `services/extensions.py` still uses it.
- Task 3: only `/memory`, `/skills`, `/tickets` left the Armory-to-Stronghold rule. The reverse rules (Stronghold or Portcullis to Armory, for example `/connections`, `/skills`, `/memory`) still list prefixes that Armory no longer serves; left alone as out of scope.
- Task 4: the file TTL also changed from 6 hours to 1 hour in the PDF and media stores (tuning defaults, both configs, both runtime fallbacks, docs, the PDF merger page note). The PDF merger card now passes `expires_at`. Media job cards were left alone (their file type has no expiry and the media page lists expiry itself).
- **Open question 2, caps measured:** the 5 MB and 50 MB caps belong to `DownloadRegistry`, which only the server-manager log export uses. Media downloads (500 MB per file, 2048 MB per session) and PDF merges (100 MB per file, 500 MB per account) use their own stores and caps, so media does not hit the 5 MB cap. Nothing changed.
- **Open question 3:** the Armory Admin "Ticket settings" page was not touched (its removal belonged to the skipped part of Task 2).
- Not run: `pnpm` for `armory_admin` (nothing in it changed). The `libs/citadel_auth` test `test_catalog_flow.py` could not be collected (no `fastapi` in the Armory venv); the other library tests pass.
- Treasury also holds a `citadel_auth` copy; the sync updated it, its suite was not run.
- `docs/deployment.md` had four statements about Armory notes, memory and skills that Task 5 corrected.

## Final results

| App | After Tasks 1 to 4 |
|---|---|
| Armory | 1237 passed, 1 skipped, 280 deselected |
| Stronghold | 1077 passed |
| Portcullis | 1175 passed, the same 2 known failures |
| Legion | 1489 passed, 6 deselected |
| libs/citadel_auth | 102 passed (without `test_catalog_flow.py`) |
| ember | `vue-tsc -b` clean, `vite build` ok, 203 files, 2403 tests passed |

Commits on `plan-22-armory-cleanup`: `45e667cf` (Task 1), `e517f8f2` (Task 2, trimmed), `05017b7b` (Task 3), `f3cedc5e` (Task 4), plus the Task 5 docs commit. Not pushed.
