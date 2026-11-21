# Plan 20j: Remove The Old Notes And Memory Routes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take out the user-facing code of the two systems the Brain replaced: Stronghold's private notes (`/notes` with its Laya tag routes) and the assistant-memory routes (`/memory`, kept by Armory), their Portcullis proxies and Ember's Memory page. Nothing else changes behaviour.

**Architecture:** Three cuts, each ending with working, tested software. Stronghold loses the routes, the tag suggestion and tag generation code and the Armory memory client calls, but keeps two purge routes and the small legacy notes store the Obsidian publishing code still imports (Plan 22 removes those). Portcullis loses the two proxy routers but keeps the delete-account purge calls. Ember loses the Memory page, route, nav entry and capability link. The long-term Brain, skills, short-term stacks, sharing and proposals are untouched.

**Tech Stack:** Python 3.12, FastAPI, pytest (Stronghold, Portcullis); Vue 3, TypeScript, Pinia, Vitest (Ember).

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md) (no users exist yet, so no data is migrated; everything old is pruned), [roadmap](2026-11-20-scope-roadmap.md) row 20j. Needs 20f (Ember Notes is the Brain browser) and 20i. The Armory side (the `memory`, `notes` and `skills` capabilities, Obsidian, brain connections) goes in Plan 22.

## Global Constraints

- Remove only what the row names: Stronghold `/notes` (list, create, read, update, delete, tags, `suggest-tags`, `generate-tag`), Stronghold `/memory` (list, create, update, delete), Portcullis `/api/notes` and `/api/memory`, Ember's Memory page. `/skills` and every `/brain*`, `/stack*`, `/brains*` route stays.
- Keep the two purge routes `DELETE /notes/accounts/{uid}` and `DELETE /memory/accounts/{uid}` in Stronghold, and the matching purge calls in Portcullis' delete-account list (`("memory", ...)`, `("notes", ...)`). Reason: Armory still stores memory and notes until Plan 22, and a deleted account's data must still be purged. Plan 22 removes them together with the Armory capabilities.
- Keep `src/notes/store.py` (`NotesService`, `Note`, `NoteNotFound`, `purge_owner`) because `src/brains/promotions.py`, `routes.py` and `suggestions.py` import it until Plan 22. Move `normalize_tags` into `src/brain/records.py` first so the Brain no longer imports the legacy module; `notes/store.py` and `brains/suggestions.py` then import it from there.
- Keep the Treasury `notes` collection entry in `src/schema/catalog.py` and the service-auth path prefixes `/notes` and `/memory` in `apps/portcullis/src/citadel_auth/policy.py` (the purge routes need them). Record both as Plan 22 clean-ups.
- No data is deleted or migrated by this plan. Old notes and Armory memories stay where they are, unreachable from any page, until Plan 22 and the prune the spec names. Say so in the report (the user may want a prune script; do not write one).
- Removing a route also removes its audit actions (`notes.create` and the other `notes.*`, `memory.*` actions). Do not add replacements.
- Ember rules: no reduced motion (never add a reduced-motion rule, media query or test); `architecture.test.ts`; shared tests that list the nav must be updated, not weakened. The Notes route `/notes` stays and is the Brain's file browser.
- Python: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider` from each app folder (in a worktree the `.venv` folders may be empty; then run the main checkout's `.venv\Scripts\python.exe -u -m pytest ...` from the worktree's app folder and say so). Ember: `pnpm exec vue-tsc -b` and `pnpm test`. Use `uv` and `pnpm`, add no dependency. Never read `.env*` or `secrets/`.
- Out of scope: anything in `apps/armory`, the Obsidian publishing routes (`/brains/notes/{id}/review`, `/promote`, `/suggestions/review`), the Ember Brains page, a data prune, an export of old notes.

## Assumptions to check while working

Record each result in "Changes found during work".

- (a) `normalize_tags` is imported only by `src/brain/files.py`, `src/brain/records.py`, `src/brains/suggestions.py` and `src/notes/*`. Grep `normalize_tags` and `NotesService` across `apps/stronghold/src` and `tests` first.
- (b) Nothing outside `src/notes/` uses `TagWriter` or `TagSuggester` (no `app.state` entry). Grep `tag_writer`, `tag_suggestions`, `TagWriter`, `TagSuggester`.
- (c) `MemoryClient.request`, `MemoryNote` and `MemoryError` are used only by `src/memory/routes.py` and `tests/test_memory.py`. Only `purge` stays.
- (d) Nothing else in Portcullis (outside client allow lists, permission tables, the body limit) names `/api/notes` or `/api/memory`. Grep the whole `apps/portcullis/src`. If an allow list does, remove the entry too.
- (e) Ember: a saved sidebar arrangement or pinned list may hold the path `/memory`. Read how `NavRail.vue` and the sidebar store treat a saved path that no longer exists; if an unknown path is not ignored, make it ignored and add a test.
- (f) Nothing else in Ember imports `features/memory/` (the earlier grep found only the router). Grep again, including `MEMORY_TEXT_MAX`, `MemoryClient`, the string `"memory"` in `router/capabilityPages.ts` and the nav, overview and capabilities tests.
- (g) Other apps (`ember_admin`, `portcullis_admin`, `legion_admin`, `armory_admin`, `stronghold_admin`, `treasury_admin`) do not call `/api/notes` or `/api/memory`. Grep each `src`.

## Baseline

Fill in before changing anything (each app):

- Stronghold: 1,076 passed (188.49 s).
- Portcullis: 1,113 passed, 2 known failures (1,016.02 s). `test_secret_box.py::test_an_invalid_key_in_env_stops_startup` and `test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown` both reject `http://127.0.0.1:0`.
- Ember: `pnpm exec vue-tsc -b` passed. `pnpm test` passed 2,403 tests in 204 files.

## File Map

| File | Change |
|---|---|
| `apps/stronghold/src/brain/records.py` | Modify: define `normalize_tags` (moved) |
| `apps/stronghold/src/notes/store.py`, `apps/stronghold/src/brain/files.py`, `apps/stronghold/src/brains/suggestions.py` | Modify: import `normalize_tags` from `src.brain.records` |
| `apps/stronghold/src/notes/tag_suggestions.py`, `tag_writer.py` | Delete |
| `apps/stronghold/src/notes/routes.py` | Modify: purge route only |
| `apps/stronghold/src/memory/routes.py`, `client.py` | Modify: purge route and `MemoryClient.purge` only |
| `apps/stronghold/tests/test_notes.py`, `test_memory.py` | Modify: keep the purge tests only |
| `apps/stronghold/tests/test_note_generate_tag.py`, `test_note_tag_suggestions.py` | Delete |
| `apps/stronghold/tests/test_legacy_routes_removed.py` | Create |
| `apps/stronghold/README.md` | Modify: route table and the Notes and memory section |
| `apps/portcullis/src/routes/notes.py`, `memory.py` | Delete |
| `apps/portcullis/src/app.py` | Modify: drop the two includes and imports |
| `apps/portcullis/tests/test_notes.py`, `test_memory.py` | Modify or delete (see Task 2) |
| `apps/portcullis/tests/test_legacy_routes_removed.py` | Create |
| `apps/portcullis/README.md` | Modify: remove the route tables, keep the purge sentences |
| `apps/ember/src/features/memory/` | Delete (view, test, `api/MemoryClient.ts` and its test) |
| `apps/ember/src/router/index.ts`, `router/pages.ts`, `router/capabilityPages.ts` | Modify: remove the Memory entries |
| Ember tests that list the nav | Modify (NavRail, AccountView, SidebarEditor, Overview, Capabilities tests) |
| Ember docs (README or AGENTS.md lines about the Memory page) | Modify |

---

### Task 1: Stronghold

**Files:** see the file map rows for Stronghold.

**Interfaces:**
- Consumes: nothing new.
- Produces: `src.brain.records.normalize_tags(raw: list[str]) -> list[str]` (same behaviour and errors as before: trims, lowercases, drops repeats, `ValueError` for an empty, too long or badly formed tag; keep the constants `TAG_MAX = 30`, `MAX_TAGS = 10` and the `_TAG` pattern it uses, defined beside it). After this task Stronghold answers `404` for every `/notes` and `/memory` path except the two `accounts/{uid}` purge routes.

- [x] **Step 1: Write the failing test**

Create `apps/stronghold/tests/test_legacy_routes_removed.py`:

```python
import pytest

from src.brain.records import normalize_tags


@pytest.mark.parametrize("method, path", [
    ("GET", "/notes"), ("POST", "/notes"), ("GET", "/notes/tags"), ("POST", "/notes/suggest-tags"),
    ("POST", "/notes/generate-tag"), ("GET", "/notes/" + "a" * 32), ("PUT", "/notes/" + "a" * 32),
    ("DELETE", "/notes/" + "a" * 32), ("GET", "/memory"), ("POST", "/memory"), ("PUT", "/memory/1"), ("DELETE", "/memory/1"),
])
def test_the_old_routes_are_gone(client, method, path):
    assert client.request(method, path, json={}).status_code == 404


def test_the_purge_routes_stay(client):
    assert client.delete("/notes/accounts/u-9").status_code == 204


def test_normalize_tags_lives_with_the_brain_records():
    assert normalize_tags([" Tea ", "tea", "Green_Tea"]) == ["tea", "green_tea"]
    with pytest.raises(ValueError):
        normalize_tags(["bad tag!"])
```

The memory purge route needs the `armory` fixture; its existing test in `tests/test_memory.py` (`test_purge_deletes_the_owner_once_and_reports_a_refusal`) stays and covers it.

- [x] **Step 2: Run it and see it fail**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_legacy_routes_removed.py`
Expected: FAIL (`ImportError: cannot import name 'normalize_tags' from 'src.brain.records'`).

- [x] **Step 3: Implement**

Check assumptions (a), (b), (c) with the greps they name.

1. `src/brain/records.py`: copy `normalize_tags` and the constants and pattern it needs (`TAG_MAX`, `MAX_TAGS`, `_TAG`) from `src/notes/store.py` into `records.py`, then replace the existing `from src.notes.store import normalize_tags` in `records.py` with the local definition. In `src/notes/store.py` delete its own definition and constants and add `from src.brain.records import MAX_TAGS, TAG_MAX, normalize_tags` (keep any other name `store.py` still uses; check with a type check or by running the tests). Change `src/brain/files.py` and `src/brains/suggestions.py` to import `normalize_tags` from `src.brain.records`. Avoid an import cycle: `records.py` must not import from `src.notes`.
2. Delete `src/notes/tag_suggestions.py`, `src/notes/tag_writer.py`, `tests/test_note_tag_suggestions.py`, `tests/test_note_generate_tag.py`.
3. `src/notes/routes.py`: keep only the router, the purge route `DELETE /notes/accounts/{uid}` (same code, same 204 and the 503 on a storage error through `_fail`) and what it imports. Delete every other route and model.
4. `src/memory/routes.py`: keep only `router = APIRouter(prefix="/memory", tags=["memory"])`, `get_memory` and the purge route. `src/memory/client.py`: keep `MemoryClient.__init__` and `purge`; delete `request`, `MemoryNote`, `MemoryError`, `_MESSAGES` and imports they alone used.
5. `tests/test_notes.py`: keep only `test_purging_an_account_removes_only_its_notes` and `test_a_purge_that_cannot_reach_storage_says_so` (with the helpers they use); delete the rest. `tests/test_memory.py`: keep only `test_purge_deletes_the_owner_once_and_reports_a_refusal` (and its helpers); delete the rest.
6. `README.md`: in the route table remove the `/notes/...` and `/memory/...` rows' route text but keep a single row saying the purge routes remain until Plan 22; rewrite the "Notes and memory" section (around line 173) to say the private-notes and memory routes are gone, the Brain replaces them, the two purge routes and `src/notes/store.py` stay for Armory's data and the Obsidian publishing code until Plan 22. Keep the purge list sentence (`DELETE /<domain>/accounts/{uid}`) as it is.

- [x] **Step 4: Run the tests**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_legacy_routes_removed.py tests/test_notes.py tests/test_memory.py tests/test_brains_promotions.py tests/test_brains_suggestions.py tests/test_brain_records.py tests/test_brain_files.py`, then the whole Stronghold suite.
Expected: pass; the total drops by the removed tests only and rises by the three new cases. No Brain, skill, stack, sharing or proposal test changes.

- [x] **Step 5: Commit**

```bash
git add apps/stronghold
git commit -m "refactor(stronghold): remove the private notes and memory routes"
```

---

### Task 2: Portcullis

**Files:** see the file map rows for Portcullis.

**Interfaces:**
- Consumes: nothing new.
- Produces: `/api/notes` and `/api/memory` no longer exist. Deleting an account still calls Stronghold's `DELETE /notes/accounts/{uid}` and `DELETE /memory/accounts/{uid}` and logs `admin.notes_purge` or `admin.memory_purge` on a failure, exactly as before.

- [x] **Step 1: Write the failing test**

Create `apps/portcullis/tests/test_legacy_routes_removed.py` (take the imports, `client` and `upstream` fixtures and `as_admin` login from `tests/test_brain_proposal_routes.py`):

```python
import pytest

from tests.test_registration import as_admin


@pytest.mark.parametrize("method, url", [
    ("GET", "/api/notes"), ("POST", "/api/notes"), ("GET", "/api/notes/tags"), ("POST", "/api/notes/suggest-tags"),
    ("POST", "/api/notes/generate-tag"), ("GET", "/api/notes/" + "a" * 32), ("DELETE", "/api/notes/" + "a" * 32),
    ("GET", "/api/memory"), ("POST", "/api/memory"), ("PUT", "/api/memory/1"), ("DELETE", "/api/memory/1"),
])
def test_the_old_routes_are_gone_and_nothing_is_forwarded(client, upstream, method, url):
    as_admin(client)
    upstream.requests.clear()
    answer = client.request(method, url, json={})
    assert answer.status_code in (404, 405)
    assert not upstream.requests
```

If the app answers a signed-in unknown `/api/...` path with another status (check what `/api/does-not-exist` returns first), assert that status instead, never a forward. Keep the "no forward" assertion.

- [x] **Step 2: Run it and see it fail**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_legacy_routes_removed.py`
Expected: FAIL (the routes still answer 200 or forward).

- [x] **Step 3: Implement**

Check assumption (d) with the grep it names.

1. Delete `src/routes/notes.py` and `src/routes/memory.py`; in `src/app.py` remove their imports and the two `app.include_router(...)` lines.
2. `tests/test_notes.py`: keep only `test_deleting_an_account_purges_its_notes_in_stronghold` and `test_failed_purge_never_blocks_account_deletion` with their helpers (rename the file `tests/test_notes_purge.py` with `git mv` if little else is left), delete the rest. `tests/test_memory.py`: delete the file (its tests are the proxy tests only); `tests/test_memory_purge.py` stays unchanged.
3. `README.md`: delete the `/api/memory` rows and the notes route table and the Laya tag paragraph (the lines around 217 to 220 and 415 to 428), keep the sentences about the purge on account deletion (`admin.memory_purge`, the notes purge), and add one line saying notes and memory are now the Brain (`/api/brain/files`, `/api/brain/summary`, and so on) and that the two purge calls stay until Plan 22.

- [x] **Step 4: Run the tests**

Run: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_legacy_routes_removed.py tests/test_notes_purge.py tests/test_memory_purge.py tests/test_brain_sharing_routes.py tests/test_brain_proposal_routes.py`, then the whole Portcullis suite (two known failures stay; the run takes about ten minutes, so use a long timeout or a background run).
Expected: new tests pass; counts drop by the removed proxy tests only.

- [x] **Step 5: Commit**

```bash
git add apps/portcullis
git commit -m "refactor(portcullis): remove the notes and memory proxy routes"
```

---

### Task 3: Ember

**Files:** see the file map rows for Ember.

**Interfaces:**
- Consumes: nothing new.
- Produces: no `/memory` route, no "Memory" nav entry, no `memory` capability page link. `/notes`, `/skills`, `/shares` and the rest are unchanged.

- [x] **Step 1: Write the failing tests**

Update the tests first, so they fail for the right reason. In `apps/ember/src/components/layout/NavRail.test.ts`, `features/account/AccountView.test.ts`, `features/settings/components/SidebarEditor.test.ts`, `features/overview/OverviewView.test.ts` and `features/capabilities/views/CapabilitiesView.test.ts`: remove `"Memory"` / `"/memory"` from every expected nav list, fixture list and arrangement (where a test used `/memory` only as an example path for pinning, hiding or ordering, swap it for `/skills`). In `router/` tests add (next to the existing router or pages test; create `router/pages.test.ts` if none exists):

```ts
import { describe, expect, it } from "vitest";
import { NAV_PAGES } from "./pages";
import { dedicatedCapabilityPage } from "./capabilityPages";

describe("the Memory page is gone", () => {
  it("has no nav entry and no capability link", () => {
    expect(NAV_PAGES.map((page) => page.to)).not.toContain("/memory");
    expect(NAV_PAGES.map((page) => page.label)).not.toContain("Memory");
    expect(dedicatedCapabilityPage("memory")).toBeUndefined();
  });
});
```

Use the real export names of `router/pages.ts` (the plan assumes `NAV_PAGES`; read the file). Check assumption (e): if the sidebar arrangement keeps a saved path that no longer exists, add a test that a saved arrangement naming `/memory` is shown without it and without an error, then fix the code to match.

- [x] **Step 2: Run them and see them fail**

Run (from `apps/ember`): `pnpm exec vitest run src/router src/components/layout/NavRail.test.ts src/features/account src/features/settings src/features/overview src/features/capabilities`
Expected: FAIL (the Memory entries still exist).

- [x] **Step 3: Implement**

Check assumptions (f) and (g) with the greps they name.

1. Delete the folder `src/features/memory/` (view, view test, `api/MemoryClient.ts`, its test).
2. `src/router/index.ts`: remove the `/memory` route record. `src/router/pages.ts`: remove the Memory entry. `src/router/capabilityPages.ts`: remove the `memory` line.
3. If a grep finds the word "Memory page", `/memory` or `MemoryClient` in Ember docs (`apps/ember/README.md`, `AGENTS.md`), update only those statements.
4. Do not touch the memory control in the chat header (`StackMenu`, `StackPanel`): that is short-term memory.

- [x] **Step 4: Run the tests**

Run: `pnpm exec vitest run src/router src/components src/features/account src/features/settings src/features/overview src/features/capabilities src/architecture.test.ts src/radiusScale.test.ts`, then `pnpm exec vue-tsc -b` and `pnpm test`.
Expected: pass; the total drops by the deleted Memory tests and rises by the new ones.

- [x] **Step 5: Commit**

```bash
git add apps/ember
git commit -m "refactor(ember): remove the Memory page"
```

---

## Final checks

- [x] Run each suite once more and record the counts against the baselines.
- [x] Grep the repo (not `node_modules`, `.venv`, `.worktrees`) for `api/notes`, `api/memory`, `NotesClient`, `MemoryClient` and `features/memory`, and update only the statements this plan makes false. Record in "Changes found during work" every remaining mention that belongs to Plan 22 (Armory capabilities, policy path prefixes, schema catalog entry).
- [x] Roadmap row 20j links this plan: `[Written](2026-11-21-plan-20j-remove-old-notes-and-memory.md)`.

## Manual checklist (the user runs these; do not claim them done)

- [ ] Start Stronghold, Portcullis and Ember. The nav has no Memory entry; opening `/memory` shows the app's not-found or default page, not an error screen. Notes, Skills and Shares still open.
- [ ] A signed-in `GET /api/notes` and `GET /api/memory` answer 404 (or the app's unknown-route answer) and Stronghold's log shows no call.
- [ ] Delete a test account that has an old note and an Armory memory: both purges still run (no `admin.notes_purge` or `admin.memory_purge` error in the log).
- [ ] The Brain still works end to end: create a file on the Notes page, find it with search, an agent reads it, a skill is still listed.
- [ ] A saved sidebar order that named Memory loads without an error.

## Self-review (writer)

- Row 20j items: Stronghold notes and Laya tag routes (Task 1), `/memory` routes (Task 1), Portcullis proxies (Task 2), Ember Memory page (Task 3), `/skills` stays (constraints).
- Placeholders: only the Baseline blanks. The Ember pages test names `NAV_PAGES`, flagged to be checked against the file.
- Risk recorded: purge routes and legacy store stay for Plan 22; no data deleted.

## Changes found during work

(The executor records here every change to a snippet, the result of assumptions a to g, and anything not verified.)

- Python worktree virtual environments were absent. Both apps ran with their main checkout's `.venv/Scripts/python.exe` using `-B -u -m pytest -q -p no:cacheprovider --tb=short` and isolated worktree temp paths. Windows sandbox fixture setup failed before any test assertions on the first attempts. The reported baselines used host execution with worktree temp paths. Ember used the locked dependencies installed in its worktree.
- (a) The only production normalization imports were in `brain/files.py`, `brain/records.py`, `brains/suggestions.py` and `notes/`. Obsidian's routes, promotions and suggestions still need the notes store. `brain/records.py` already re-exported normalization, so the new test checks its defining module. RED: 11 failed, 3 passed. Active routes responded with their old statuses and the function still belonged to `src.notes.store`.
- (b) Only Stronghold's legacy notes routes called `TagWriter` or `TagSuggester`. Their other references were the deleted tests. No app-state wiring existed.
- (c) Only Stronghold's legacy memory router used the client request method, `MemoryNote` and `MemoryError`. The catalog routing test used the old GET route, so it now checks the same two Armory addresses through the retained memory purge. `src/api.py` still wires both purge routers.
- Stronghold's notes purge test now seeds both owners through `NotesService`. Three Obsidian publishing tests also use store-backed test setup in place of `POST /notes`. All publishing assertions were preserved.

- Stronghold task run: 114 focused tests passed, then 1,001 full-suite tests passed. Removed 89 cases: `test_notes.py` (42), `test_memory.py` (14), `test_note_generate_tag.py` (15) and `test_note_tag_suggestions.py` (18). Added 14 cases. Commit `59dbd605`.
- Portcullis signed-in `GET /api/does-not-exist` returned 404 with zero upstream requests. The plan's 404/405 assertion fits the app.

- (d) Only the two Portcullis proxy modules named `/api/notes` or `/api/memory` in `src/`. No allow list, permission entry or body-limit entry needed removal. The service-auth prefixes and `routes/admin.py` purge entries stayed.
- Portcullis RED: all 11 proxy cases failed while the old routes returned success. Notes tests moved to `test_notes_purge.py`, retaining its two purge assertions. Removed 17 proxy cases: 11 from `test_notes.py` and six from `test_memory.py`. `test_memory_purge.py` stayed unchanged.

- (e) The sidebar store preserves unknown paths in saved prefs. The rail and sidebar editor arrange only current page objects, so obsolete paths are ignored on render. Added a saved-arrangement rail test with pinned Memory and Skills and hidden Notes. The reset and modified indicators did read the raw paths. Updated both to check known NAV_PAGES while retaining the saved data.
- (f) Outside the removed feature, only the Ember router imported `features/memory`. The real exports were `NAV_PAGES` and `dedicatedCapabilityPage`, and the existing router test now covers the old URL, nav and capability link. No separate MemoryClient test or stale Ember README/AGENTS statement existed.
- (g) No calls to either old API in Portcullis Admin, Legion Admin, Armory Admin, Stronghold Admin or Treasury Admin. This checkout has no `apps/ember_admin` directory.
- Ember RED: 16 failed, 190 passed. All failures concerned the current Memory route or rendered nav. The first focused run after the removal found two more NavRail expectations expressed as the numeric count 9. Both now expect 8, keeping the loading-state assertions. Existing test changes: NavRail (six), AccountView (one), SidebarEditor (seven), OverviewView (one), CapabilitiesView (one). Removed 12 `MemoryView.test.ts` cases plus the automatically discovered MemoryView case in `pageLayout.test.ts`. Added four cases in total.
- Ember's independent red/green checks ran during Portcullis's full suite. Commits are in task order.

- Saved preferences containing only unknown paths made the Settings editor show Reset. The added SidebarEditor case failed first (one failed, 13 passed), then passed after both Settings indicators used the known page catalog. `navArrangement.test.ts` passes its existing page fixture to the modified check with its original expectations.
- Read-only code review confirmed purge and publishing wiring. The Portcullis regression matrix follows the plan and lacks a separate `PUT /api/notes/{id}` case. A separate signed-in PUT probe returned 404 and sent zero upstream requests. Stronghold's regression matrix also exercises the corresponding PUT.
- Stronghold final rerun: 1,001 passed in 136.38 s; baseline 1,076, 89 removed and 14 added.

- Ember verification after the saved-sidebar fix: 421 focused cases passed, including architecture, radius scale and the navigation helper. Both `pnpm exec vue-tsc -b` runs passed. Both full runs passed 2,394 cases in 203 files (2,403 before; 13 removed including the auto-discovered layout test, four added).
- The copied normalization function, tag constants and regex match the original source. Stronghold's catalog entry and notes store, both purge routers, the purge-only client and the Obsidian publishing callers remain for Plan 22. Portcullis keeps its two account-delete purge entries, tests and audit error names. The shared auth library and its Stronghold, Portcullis, Armory, Legion and Treasury copies retain the legacy policy prefixes.
- Plan 22 also retains responsibility for Armory's `memory`, `notes`, `skills` and Obsidian capabilities, connections and Brain admin. The unused Portcullis `src/services/notes.py` predates Plan 20j and is outside its removal list.
- Repo search for `api/notes`, `api/memory`, `NotesClient`, `MemoryClient` and `features/memory` found only removal tests, the retained Stronghold purge client and wiring, older documentation and reference-only Ember Web code, tests and design references. The five searched terms have no remaining matches in maintained production Ember or Portcullis. Main's local roadmap already contains one row 20j link, so this branch leaves the roadmap untouched.
- Vault notes to update after integration: `Brain/Projects/Citadel.md`, `stronghold.md`, `portcullis.md`, `ember.md`, `armory.md` and `ember_web.md`, plus `Brain/Notes/Decision - Notes, memory, skills and brains merge into one personal Brain with a global brain.md`. The vault was read-only for this task.
- Manual checklist remains pending. Existing user data was neither migrated nor pruned.

### Existing test expectations and fixtures

- Stronghold `test_catalog_peers.py`: the catalog-address test now expects 204 from the memory purge. `test_notes.py::test_purging_an_account_removes_only_its_notes` and the three publishing cases named below changed setup only. `test_brains_routes.py`: `test_ai_review_consent_usage_dismiss_and_invalid_output`, `test_review_agent_failure_is_a_503`, and `test_promote_review_and_reconcile`.
- Portcullis `test_notes_purge.py`: retained `test_deleting_an_account_purges_its_notes_in_stronghold` and `test_failed_purge_never_blocks_account_deletion` from the original notes test file. Their assertions and the separate memory purge tests are unchanged.
- Ember `NavRail.test.ts` (six): shows one icon-only link per page; puts pinned pages first; leaves hidden pages out; draws no pages until the arrangement has loaded; leaves administrator-hidden pages out; draws no pages until the hidden list has loaded.
- Ember `SidebarEditor.test.ts` (seven): lists the default order; moves a page with its arrow; reorders by dragging; shows the drop slot; drops onto the slot as onto its row; offers Reset for a modified arrangement; omits administrator-hidden pages.
- Ember `AccountView.test.ts` (one): lists pages the tab bar leaves out. `OverviewView.test.ts` (one): offers only permitted pages. `CapabilitiesView.test.ts` (one): links the remaining dedicated pages through their permissions.

- Portcullis task run: 122 focused cases passed. Full suite: 1,107 passed and the same two baseline failures in 833.28 s (17 cases removed, 11 added). Commit `a90f4304`.

### Verification commands

Python run prefix, from each app: main checkout's `.venv/Scripts/python.exe -B -u -m pytest -q -p no:cacheprovider --tb=short --basetemp <isolated temp path>`. Full runs used this prefix without a test selection.

- Stronghold focused selection: `tests/test_legacy_routes_removed.py tests/test_notes.py tests/test_memory.py tests/test_brains_promotions.py tests/test_brains_suggestions.py tests/test_brain_records.py tests/test_brain_files.py tests/test_brains_routes.py tests/test_catalog_peers.py`.
- Portcullis focused selection: `tests/test_legacy_routes_removed.py tests/test_notes_purge.py tests/test_memory_purge.py tests/test_brain_sharing_routes.py tests/test_brain_proposal_routes.py`. The separate signed-in unknown-route and PUT checks used disposable worktree test files with `-p tests.conftest`.
- Ember focused command: `pnpm exec vitest run src/router src/components src/features/account src/features/settings src/features/overview src/features/capabilities src/architecture.test.ts src/radiusScale.test.ts src/utils/navigation/navArrangement.test.ts`. Full checks used `pnpm exec vue-tsc -b` and `pnpm test`.

### Final reruns

| App | Baseline | Final | Change |
|---|---:|---:|---|
| Stronghold | 1,076 passed | 1,001 passed | 89 removed, 14 added |
| Portcullis | 1,113 passed, 2 known failures | 1,107 passed, same 2 failures (688.92 s) | 17 removed, 11 added |
| Ember | 2,403 passed, type-check passed | 2,394 passed, type-check passed | 13 removed, 4 added |

The worktree retains an untracked `apps/ember/CLAUDE.md` generated by the SourceOfTruth hook. It is outside the commits.
