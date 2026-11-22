# Plan 22b: Remove the Obsidian chain (second brain, instance brain, personal brain connections) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everything that connected Citadel to an Obsidian vault is gone: Ember's Brains page and the chat's "save to second brain" controls, Portcullis `/api/brains` and `/api/admin/brain`, Stronghold `/brains` and the legacy notes store, Armory's `obsidian` and `vault` capabilities and the Armory Admin Brain page. The Brain (short-term, long-term, global, shares, proposals) stays untouched.

**Architecture:** A removal plan, like 20j and 22. Callers go first, then the callee, so no commit leaves a broken call: Ember, then Portcullis, then Stronghold, then Armory. No stored data is deleted by code: old Treasury collections (`notes`, brain connections, promotions, suggestions) and Armory's index files stay on disk, unused. One Portcullis migration drops the two chat columns and the publish permission, because Portcullis owns a schema.

**Tech Stack:** Python 3.11+ FastAPI and FastMCP, SQLAlchemy and Alembic (Portcullis), Vue 3 + TypeScript + Pinia + Vitest (Ember, Armory Admin), `uv`, `pnpm`.

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md) ("Obsidian is removed for now", "Changes from today"). Audit decision D2 in [2026-11-20-scope-audit.md](2026-11-20-scope-audit.md). Roadmap row 22b. It finishes what Plans 15, 20j and 22 left in place.

## Global Constraints

- Remove only what a task names. A grep hit on a live caller the plan did not name stops that item: record it under "Changes found during work" and keep the code.
- **Keep (do not touch):** the new Brain everywhere (`apps/stronghold/src/brain/`, `src/mcp_tools/`, `apps/portcullis/src/routes/brain_files.py`, `brain_sharing.py`, `brain_proposals.py`, `stronghold_brain_settings.py`, Ember `features/notes`, `features/sharing`, `features/proposals`, `features/global`), Stronghold Admin's "Brain settings" page, Armory's other capabilities (`repo_reader` keeps its own folder setting), Armory's registration in Treasury (`service_catalog.py`, the `DB_GATEWAY_*` variables, `require_internal_origin`), the extension proxy, `services/connections.py`, `connection_admin.py` and the Armory Admin Connections page (Plan 22 kept them).
- Models only through Legion: Armory's Obsidian embeddings called Ollama directly. They go with the capability. No replacement.
- No data migration and no prune script. The only schema change is the one Portcullis migration in Task 2.
- `libs/citadel_auth` is edited only in `libs/citadel_auth/`, then `python scripts/sync_citadel_auth.py`; `--check` must exit 0 at the end.
- Never read, print or write `.env*`, `secrets/` or key files. Entries for the removed settings in `.env.example` files are listed in the final report for the user; do not open those files.
- Use `uv` and `pnpm`. Add no dependency. One commit per task, each ending with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Do not push.

## Baseline (record before the first edit)

Branch `plan-22b-remove-obsidian-chain` from `main` (Plans 22, 23, 24 on `main`, at `b923db42` or later; if not, stop and report). If Plan 25 or 24b is open at the same time, they touch `libs/citadel_auth` (other files), `api.py`, `app.py` and READMEs; merge one, then `git rebase main` the other.

Run once: Armory, Stronghold, Portcullis (about 13 minutes, 2 known failures: `test_secret_box.py::test_an_invalid_key_in_env_stops_startup`, `test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`), Legion with `uv run --no-sync python -u -m pytest -q -p no:cacheprovider` (in a worktree with empty `.venv` folders use the main checkout's interpreter from the app folder); Ember, Armory Admin with `pnpm exec vue-tsc -b` and `pnpm test`. Record counts under "Baseline results".

## Assumptions to check (record each result under "Changes found during work")

- **(a)** Stronghold's `src/brain/global_routes.py` imports `need` and `permissions` from `src/brains/routes.py` (line 13). They must move before `src/brains/` is deleted (Task 3).
- **(b)** Stronghold `src/api.py` builds `app.state.brain_gateway = BrainGateway(armory_client, keyring)` (line ~136), includes `brains_routes.router` (line ~222) and runs `instance_migration` at startup. All three go. `NotesService` is also built in `api.py`; `git grep -n "NotesService\|notes_service\|app.state.notes" -- apps/stronghold/src` lists its users (`brains/promotions.py`, `brains/routes.py`, `brains/suggestions.py`, `notes/routes.py`, `notes/store.py`). After Task 3 none may remain.
- **(c)** The new Brain has no dependency on `src/notes/` or `src/brains/` other than (a). Check `git grep -n -E "src\.notes|src\.brains" -- apps/stronghold/src apps/stronghold/tests`.
- **(d)** Portcullis `chats.save_to_second_brain` and `chats.second_brain_scope` are columns (models line 36 to 37; migration `0025` added the scope column; find the migration that added `save_to_second_brain` with `git grep -n save_to_second_brain -- apps/portcullis/migrations`). The permission `brain.instance.publish` was inserted by `0025`. The latest migration is `0027_outside_clients.py`; the new one is `0028`.
- **(e)** Portcullis `services/notes.py` is unused (Plan 20j report). Confirm with `git grep -n "services.notes\|services import notes" -- apps/portcullis/src`.
- **(f)** Portcullis' delete-account list in `routes/admin.py` (around line 312) still has `("notes", "Notes")` and `("brains", "Brain connections")`. Both go in Task 2, and their Stronghold routes go in Task 3. Do both in this order so no purge call hits a missing route in a half-built state.
- **(g)** Armory's `vault` capability reads the user's vault folder (`MCP_VAULT_DIR`, config line ~97); `repo_reader` shares the config comment only. Compose may mount the Brain vault folder into Armory (`git grep -n -i "vault\|obsidian" -- docker-compose*.yml`); remove only those mounts and variables.
- **(h)** Armory Admin's Brain page uses `src/api/BrainClient.ts`, `src/views/BrainView.vue` and its test, `router/index.ts` and `router/pages.ts`. Armory's `environment_settings.py` lists the Obsidian settings (`Spec("obsidian_*")`) that the Settings page shows.
- **(i)** Ember's chat second-brain feature touches `src/api/types.ts` (lines ~254 to 255), `features/chat/api/ChatsClient.ts`, `features/chat/services/ConversationStorage.ts`, `features/chat/stores/chat.ts`, `features/chat/components/ChatSettingsMenu.vue` and their tests; the Brains page is `features/brains/` plus `router/index.ts`, `router/pages.ts`, and the nav and capability-page lists.

## File map

| Area | Remove | Change |
|---|---|---|
| Ember | `src/features/brains/` (page, client, form, test); second-brain props, events and store state in the chat feature | `router/index.ts`, `router/pages.ts`, nav and sidebar tests, `api/types.ts`, chat files above |
| Portcullis | `routes/brains.py`, `services/brain_client.py`, `services/second_brain.py`, `services/notes.py`, their tests | `app.py` (two includes), `routes/chats.py`, `services/chat_service.py`, `models/chat.py`, `routes/admin.py` (purge list), new `migrations/versions/0028_remove_second_brain.py`, permission lists, README |
| Stronghold | `src/brains/` (all six files), `src/notes/` (`store.py`, `routes.py`), their tests | new `src/brain/access.py` (the two helpers), `src/brain/global_routes.py` (import), `src/api.py`, `src/schema/catalog.py` (`notes` and any brain-connection entries), README |
| Armory | `src/capabilities/obsidian/`, `src/capabilities/vault/` | `src/config.py`, `src/environment_settings.py`, `src/services/app_config.py` if it names them, `src/run.py` (obsidian routes and startup), compose, README files |
| Armory Admin | `src/views/BrainView.vue` and test, `src/api/BrainClient.ts` | `router/index.ts`, `router/pages.ts`, nav test |
| `libs/citadel_auth` | `/brains/resolve`, `/brains/instance-migration`, `/notes` paths and the `/brains`, `/notes` prefixes | `policy.py`, then sync |

---

### Task 1: Ember removes the Brains page and the second-brain controls

**Files:**
- Delete: `apps/ember/src/features/brains/` (all files).
- Modify: `apps/ember/src/router/index.ts`, `src/router/pages.ts`, the nav, sidebar and overview tests that list the page, `src/api/types.ts`, `features/chat/api/ChatsClient.ts`, `features/chat/services/ConversationStorage.ts`, `features/chat/stores/chat.ts`, `features/chat/components/ChatSettingsMenu.vue`, and every test that names a second-brain prop.
- Test: the existing nav tests and `ChatSettingsMenu` test, plus `apps/ember/src/features/chat/secondBrainRemoved.test.ts` (create).

**Interfaces:**
- Consumes: Plan 20j's rule that a saved sidebar path for a retired page is ignored (already built).
- Produces: no `/brains` route, no Brains nav entry, no `secondBrain*` or `saveToSecondBrain` field in Ember types or chat state, no `/api/chats/second-brain` call, and no second-brain toggle in the chat settings menu.

- [ ] **Step 1: Check assumption (i)** and list every test that names the removed things: `git grep -l -i -E "second_?brain|BrainsView|BrainsClient|/brains" -- apps/ember/src`.

- [ ] **Step 2: Write the failing test**

```ts
// apps/ember/src/features/chat/secondBrainRemoved.test.ts
import { describe, expect, it } from "vitest";
import router from "@/router";
import { NAV_PAGES } from "@/router/pages";

describe("second brain is gone from Ember", () => {
  it("has no /brains route and no Brains nav entry", () => {
    expect(router.getRoutes().some((r) => r.path === "/brains")).toBe(false);
    expect(NAV_PAGES.some((p) => p.to === "/brains")).toBe(false);
  });
});
```

If `router` is exported differently or `NAV_PAGES` has another name, copy the import from `src/architecture.test.ts` or the nav test and keep the two assertions.

- [ ] **Step 3: Run it; see it fail.** `pnpm exec vitest run src/features/chat/secondBrainRemoved.test.ts` from `apps/ember`.

- [ ] **Step 4: Remove.** Delete the Brains feature; drop the route, nav entry and any capability link; remove the second-brain fields from `types.ts`, `ChatsClient.ts` (both request shapes and the `secondBrainAvailability` call), `ConversationStorage.ts`, the chat store (`secondBrainOnline`, `secondBrainPending`, `draftSecondBrain`, scope and the toggle actions) and `ChatSettingsMenu.vue` (the select, the checkbox and their events). Update each test only to drop what was removed; say which tests changed.

- [ ] **Step 5: Run `pnpm exec vue-tsc -b`, `pnpm test`, `pnpm exec vite build`.** `architecture.test.ts` and `radiusScale.test.ts` stay green.

- [ ] **Step 6: Commit.** `git commit -m "refactor(ember): remove the Brains page and the second-brain chat controls"`

---

### Task 2: Portcullis removes the brains routes, second-brain chat fields and publish permission

**Files:**
- Delete: `apps/portcullis/src/routes/brains.py`, `src/services/brain_client.py`, `src/services/second_brain.py`, `src/services/notes.py` (assumption (e)), and their tests (`git grep -l -E "routes.brains|brain_client|second_brain|services.notes|api/brains|api/admin/brain" -- apps/portcullis/tests`).
- Create: `apps/portcullis/migrations/versions/0028_remove_second_brain.py`.
- Modify: `src/app.py` (drop `from src.routes import brains` and the two `include_router(brains...)` lines), `src/routes/chats.py` (the body fields, `/second-brain` route, `_second_brain_available`, the save and scope logic, the `chat.second_brain` audit call), `src/services/chat_service.py`, `src/models/chat.py`, `src/routes/admin.py` (drop `("notes", "Notes")` and `("brains", "Brain connections")` from the purge list), the permission constant and seed lists that name `brain.instance.publish` (`git grep -n "brain.instance.publish\|BRAIN_INSTANCE" -- apps/portcullis apps/portcullis_admin apps/ember`), README, `configs/README.md` if it mentions them.
- Test: `apps/portcullis/tests/test_migrations.py` (extend), the chat route tests, `test_account_purge_forwarding.py` (Plan 22 renamed it; it checks the notes purge, change it to a domain that stays).

**Interfaces:**
- Consumes: Task 1 (Ember no longer calls these).
- Produces: no `/api/brains`, `/api/admin/brain`, `/api/chats/second-brain`; chat create, patch and detail responses carry no `save_to_second_brain`, `second_brain_scope` or `second_brain_available`; the `chats` table lacks both columns; the permission `brain.instance.publish` is deleted from `permissions` and `role_permission`; the delete-account list has no `notes` or `brains` entry.

- [ ] **Step 1: Check assumptions (d), (e), (f).** Find the migration that added `save_to_second_brain`. Record the real names.

- [ ] **Step 2: Write the failing tests**

```python
# in apps/portcullis/tests/test_migrations.py (copy the helper this file uses to upgrade a fresh database to head)
def test_second_brain_columns_and_permission_are_dropped(upgraded_database):
    # upgraded_database: the fixture or helper the other migration tests in this file use
    columns = {c["name"] for c in inspect(upgraded_database).get_columns("chats")}
    assert "save_to_second_brain" not in columns and "second_brain_scope" not in columns
    with upgraded_database.connect() as conn:
        left = conn.execute(text("SELECT COUNT(*) FROM permissions WHERE name='brain.instance.publish'")).scalar()
    assert left == 0
```

```python
# in the chat route tests
def test_second_brain_routes_and_fields_are_gone(client, signed_in):
    assert client.get("/api/chats/second-brain", cookies=signed_in).status_code == 404
    for path in ("/api/brains/destinations", "/api/admin/brain"):
        assert client.get(path, cookies=signed_in).status_code == 404
    created = client.post("/api/chats", json={}, cookies=signed_in).json()
    assert "save_to_second_brain" not in created and "second_brain_scope" not in created
```

Use the real fixture names and the real create-chat body from the existing tests.

- [ ] **Step 3: Run them; see them fail.**

- [ ] **Step 4: Remove and migrate.** Write `0028` with `revision = "0028"`, `down_revision = "0027"`: `upgrade()` deletes the permission rows first (as `0025`'s downgrade does) and then, inside `op.batch_alter_table("chats")`, drops `save_to_second_brain` and `second_brain_scope`; `downgrade()` re-adds both columns with the same types and defaults as in `models/chat.py` today (copy them before you delete the model lines) and re-inserts the permission as `0025` did. Then remove the code in the order: `app.py` includes, route modules, chat route logic, chat service, model, purge list, permission constants.

- [ ] **Step 5: Run the Portcullis suite** (the two known failures stay). Run the migration up and down once on a scratch database through the test helper.

- [ ] **Step 6: Commit.** `git commit -m "refactor(portcullis): remove the brains routes, second-brain chat fields and publish permission"`

---

### Task 3: Stronghold removes `/brains` and the legacy notes store

**Files:**
- Create: `apps/stronghold/src/brain/access.py` (the two helpers, assumption (a)).
- Delete: `apps/stronghold/src/brains/` (`connections.py`, `gateway.py`, `instance_migration.py`, `promotions.py`, `routes.py`, `suggestions.py`), `apps/stronghold/src/notes/` (`store.py`, `routes.py`), their tests (`git grep -l -E "src\.brains|src\.notes|brains_routes|NotesService" -- apps/stronghold/tests`).
- Modify: `src/brain/global_routes.py` (import from `src.brain.access`), `src/api.py` (remove the imports, `BrainGateway`, the migration lock and startup call, `NotesService`, the `brains_routes` include and the notes router include), `src/schema/catalog.py` (remove the `notes` entry and any entry for brain connections, promotions or suggestions), README.
- Test: `apps/stronghold/tests/test_brain_access.py` (create), the catalog and peer tests.

**Interfaces:**
- Consumes: Task 2 (Portcullis no longer calls `/brains` or `/notes`).
- Produces: `src/brain/access.py` with `async def permissions(request, who=Depends(current_requester)) -> set[str]` and `def need(granted: set[str], permission: str) -> None`, behaving exactly as the old versions in `src/brains/routes.py` (lines 44 to 60). Stronghold has no `/brains` or `/notes` route and no `DELETE .../accounts/{uid}` for them.

- [ ] **Step 1: Check assumptions (a), (b), (c).** Copy the two helpers' bodies exactly.

- [ ] **Step 2: Write the failing test**

```python
# apps/stronghold/tests/test_brain_access.py
import importlib.util

import pytest
from fastapi import HTTPException

from src.brain.access import need


def test_need_refuses_a_missing_permission():
    with pytest.raises(HTTPException) as refused:
        need(set(), "brain.global.write")
    assert refused.value.status_code == 403


def test_need_allows_a_granted_permission():
    need({"brain.global.write"}, "brain.global.write")


@pytest.mark.parametrize("module", ["src.brains", "src.notes"])
def test_the_legacy_packages_are_gone(module):
    assert importlib.util.find_spec(module) is None
```

If the old `need` raised a different status or message, mirror it and keep the test's behaviour statement.

- [ ] **Step 3: Run it; see it fail** (`ModuleNotFoundError: src.brain.access`).

- [ ] **Step 4: Move, then delete.** Create `access.py`, point `global_routes.py` at it, run the Stronghold suite (green), then delete the packages and clean `api.py`, `catalog.py` and the tests. Keep `src/brain/` and `src/mcp_tools/` untouched.

- [ ] **Step 5: Run the Stronghold suite.** The route-table README rows for `/brains...` and `DELETE /notes/accounts/{uid}` go.

- [ ] **Step 6: Commit.** `git commit -m "refactor(stronghold): remove /brains and the legacy notes store"`

---

### Task 4: Armory removes `obsidian`, `vault` and the Brain admin page

**Files:**
- Delete: `apps/armory/src/capabilities/obsidian/`, `apps/armory/src/capabilities/vault/`, their tests; `apps/armory_admin/src/views/BrainView.vue`, `BrainView.test.ts`, `src/api/BrainClient.ts`.
- Modify: `apps/armory/src/config.py` (the `obsidian_*` fields and `vault_dir`), `src/environment_settings.py` (the `Spec("obsidian_*")` rows), `src/run.py` (obsidian routes and any startup or migration retry for the Instance Brain), `src/services/app_config.py` and `src/services/capability_base.py` if they name the capabilities, `apps/armory_admin/src/router/index.ts`, `router/pages.ts`, the nav and guard tests, compose (the Armory vault mount and the Obsidian and `MCP_VAULT_DIR` variables only), `apps/armory/src/capabilities/README.md` (drop the two bullets), READMEs.
- Test: `apps/armory/tests/test_capabilities_removed.py` (extend Plan 22's), the armory_admin nav test.

**Interfaces:**
- Consumes: Tasks 2 and 3 (nothing calls Armory's Brain routes or `/brains/resolve`).
- Produces: Armory registers no `tool_obsidian_*` or `tool_vault_*`; its Settings page lists no Obsidian settings; Armory Admin has no Brain page; Armory makes no call to Stronghold and no call to Ollama.

- [ ] **Step 1: Check assumptions (g) and (h).** Record what compose mounts. `repo_reader`'s folder setting stays.

- [ ] **Step 2: Write the failing tests**

```python
# append to apps/armory/tests/test_capabilities_removed.py
@pytest.mark.parametrize("name", ["obsidian", "vault"])
def test_obsidian_capabilities_cannot_be_imported(name):
    assert importlib.util.find_spec(f"src.capabilities.{name}") is None


def test_no_obsidian_setting_is_left():
    from src.environment_settings import SPECS  # the list `Spec(...)` rows live in; copy the real name from the file
    assert not [s for s in SPECS if s.key.startswith("obsidian_")]
```

Use the real names for the settings list and the `Spec` key attribute. Also extend the tool-name test: no registered name starts with `tool_obsidian_` or `tool_vault_`. armory_admin: the nav list expects no `/brain`.

- [ ] **Step 3: Run them; see them fail.**

- [ ] **Step 4: Remove.** Callers first (armory_admin page, router, nav), then Armory's `run.py` wiring and config, then the capability folders, then compose lines. Boot Armory once from an empty scratch folder on a port from `29900-29998` with a scratch identity and trust folder (never against real data): it must start with no traceback, with the capability scan lacking the two names. Record what you saw.

- [ ] **Step 5: Run Armory and Armory Admin suites** (`vue-tsc -b`, `pnpm test`, `vite build`).

- [ ] **Step 6: Commit.** `git commit -m "refactor(armory): remove the obsidian and vault capabilities and the Brain admin page"`

---

### Task 5: Auth rules, docs, sweep and report

**Files:**
- Modify: `libs/citadel_auth/citadel_auth/policy.py` and its test; READMEs of Armory, Stronghold, Portcullis, Ember, Armory Admin; `docs/deployment.md`; the capabilities READMEs; the roadmap row 22b ("Built").

- [ ] **Step 1: Write the failing policy test** in `libs/citadel_auth/tests/test_auth.py`: Armory may not call Stronghold `/brains/resolve`, `/brains/instance-migration` or `/notes/x`; Portcullis may not call Stronghold `/brains/x` or `/notes/x`; Legion's and Portcullis' other Stronghold paths still pass. Use the file's existing "may this service call this path" helper.

- [ ] **Step 2: Run it; see it fail.** Edit the policy in `libs/` (remove the three Armory paths and the `/brains`, `/notes` prefixes for Portcullis), run `python scripts/sync_citadel_auth.py`, run the test, run `python scripts/sync_citadel_auth.py --check`.

- [ ] **Step 3: Sweep.** `git grep -n -i -E "obsidian|second.brain|instance brain|api/brains|/brains|tool_vault_|tool_obsidian_|NotesService|brain_gateway" -- apps libs docs scripts docker-compose*.yml ':!docs/superpowers/plans' ':!docs/superpowers/specs' ':!*/node_modules/*' ':!*/.venv/*'`. Update only statements this plan made false. List each remaining mention with the reason it stays (a plan or spec file, a changelog line, `ember_web` which is reference only).

- [ ] **Step 4: Final suites** for every app and the library, `vue-tsc -b` and `vite build` for Ember and Armory Admin, `python scripts/check_compose.py`, `docker compose config --quiet`, `git diff --check`. Record counts under "Final results".

- [ ] **Step 5: Commit.** `git commit -m "refactor(auth): drop the Obsidian-era paths; docs and roadmap for Plan 22b"`

## Self-review

- **Spec coverage:** Obsidian removed (Tasks 3, 4); Armory never calls Stronghold again (Task 4, Task 5); Plan 15's Armory work removed (Task 4); Portcullis stops holding the Brain proxy routes of the old kind (Task 2); no Armory-direct model call left (Obsidian embeddings go in Task 4).
- **Order check:** every callee is removed after its last caller: Ember, then Portcullis, then Stronghold, then Armory, then the policy.
- **Placeholders:** names marked "copy the real name" are fixtures and list names this plan did not read; each says where to find them.
- **Risk:** `0028` is the only schema change. Its downgrade restores the columns and the permission, so a rollback is possible. Treasury data for the removed features stays.

## Open questions for the user

1. `.env.example` files may still list `OBSIDIAN_*` and `MCP_VAULT_DIR` keys. The executor may not open them; remove those lines yourself or tell me to.
2. The Armory `service_catalog.py` and `DB_GATEWAY_*` variables stay (they register Armory in Treasury). A later plan can rename them.
3. Old Treasury collections and Armory index files stay on disk. Say if you want a one-off prune script (this plan writes none).

## Manual checklist (pending after the build)

- [ ] Open Ember: no Brains page, no second-brain controls in the chat settings; Notes, Skills, Shares, Global and the memory control still work.
- [ ] Create a chat, rename it, pin it: nothing mentions a second brain.
- [ ] Delete a test account that had notes and Brain files: the purge runs with no `notes` or `brains` error and the Brain files are gone.
- [ ] Armory Admin: no Brain page; Settings has no Obsidian section; Capabilities lists neither `obsidian` nor `vault`.
- [ ] Run a Portcullis migration on a copy of a real database (`0027` to `0028`) and back.

## Baseline results

(record here)

## Changes found during work

(record here)

## Final results

(record here)
