# Plan 22c: Remove Armory's extension proxy and its Connections page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Run the five tasks straight through in the current checkout and report once at the end. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Armory no longer connects to other MCP servers on behalf of users. Ember's Capabilities page, Portcullis `/api/extensions` and `/api/admin/connections`, Armory's `extension_routes.py`, `connection_admin.py`, `services/extensions.py`, `services/connections.py` and the Armory Admin Connections page are gone. MCP connections live only in Legion (Plan 18, Legion Admin "Connections"), and per-user private extensions stay in Stronghold.

**Architecture:** A removal plan like 20j, 22 and 22b, with no new behaviour. Callers go first, then the callee: Ember, then Portcullis, then Armory, then Armory Admin, then the auth policy. No stored data is deleted by code: Armory's `extensions` and `connections` tables in `settings.db` stay on disk, unused. The `enabled_extensions` / `extension_ids` parameters that travel from Portcullis through Stronghold to Legion stay in place and carry an empty list, so no cross-service contract changes in this plan.

**Tech Stack:** Python 3.11+ FastAPI and FastMCP (Armory, Portcullis), Vue 3 + TypeScript + Pinia + Vitest (Ember, Armory Admin), `uv`, `pnpm`.

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md) (Armory "Not: Connection records. Extensions proxy"; "Changes from today": "Armory: remove ... connections, extensions proxy"). Roadmap row 22c. Finishes what Plan 22 deliberately left in place.

## Decision this plan makes (change it before building if wrong)

Shared extensions stop being a user-facing list. After this plan an administrator adds an outside MCP server as a **Legion connection** (Legion Admin, Connections, built in Plan 18), and an agent offers its tools only when the agent's `tools.allow` names them (Plan 18b). The Ember "Extensions" tab keeps the user's **private** extensions (Stronghold) and drops the shared list. Old shared extension records in Armory are not migrated; the administrator re-adds the ones still wanted as Legion connections.

## Global Constraints

- Remove only what a task names. A `git grep` hit on a live caller the plan did not name stops that item: keep the code and list it under "Findings".
- **Keep (do not touch):** Armory's capabilities, `service_catalog.py` and its Treasury registration, `require_internal_origin`, `upload_routes.py`, download routes, the Stronghold private extensions (`apps/stronghold/src/extensions/`, Portcullis `routes/user_extensions.py`, Ember `UserExtensionsClient`, `userExtensions` store, `UserExtensionModal`), Portcullis `GET /api/connection-status` and its `readiness()` helper (config issues use them), the `extensions.manage` permission and the `extensions.personal.manage` permission (permission rows live in the database; renaming or dropping them needs a migration this plan does not make), Legion's `enabled_extensions` / `extension_ids` plumbing, `tools/mcp_client/` and the tool filter.
- No new feature, route, setting, dependency or screen. No data deleted. No schema change.
- `libs/citadel_auth` is edited only in `libs/citadel_auth/`, then `python scripts/sync_citadel_auth.py`, then `python scripts/sync_citadel_auth.py --check` must exit 0. Never edit a copied `apps/*/src/citadel_auth/`.
- Never read, print or write `.env*`, `secrets/` or key files. Use `uv` and `pnpm`. No reduced-motion code anywhere (repo rule). Keep each file's line endings; edit with editor tools.
- Work in the current checkout and branch. No worktree, no new branch, no commit unless the user asks. Do not push.
- Test budget: each task runs only the test files it names, once, with the command it gives. No full suites, no Docker or compose check. Python: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider <files>` from the app folder (if it fails, use the app's `.venv\Scripts\python.exe -u -m pytest ...`). Ember and Armory Admin: `pnpm exec vitest run <files>` and, once at the end of the task, `pnpm exec vue-tsc -b`. A run over about 2 minutes: stop and say so.

## What the checks found (2026-11-22, on `main` `d4834733`)

| Area | Piece | Role today |
|---|---|---|
| Ember | `features/capabilities/api/ExtensionsClient.ts` (`GET /api/extensions`), `api/contracts/extensions.ts` (`ExtensionInfo`, `EXTENSION_SEPARATOR`), shared-extension rows in `views/CapabilitiesView.vue`, `utils/capabilityGroups.ts` (`extensionGroups`), `features/chat/stores/chat.ts` (`enabledExtensions` filled from `extensionsClient.list()`), `ChatSettingsMenu.vue` line "Extensions: ..." | Shows and enables shared extensions |
| Portcullis | `routes/server_info.py` `GET/POST/DELETE /api/extensions`; `services/mcp_server_info.py` `extensions()`, `add_extension()`, `remove_extension()`; `routes/chats.py` ~line 549 builds `extension_ids` from `info.extensions(account)`; `routes/connections.py` `/api/admin/connections` proxy routes (the `readiness()` helper and `/api/connection-status` stay) | Pass-through to Armory |
| Armory | `src/extension_routes.py`, `src/connection_admin.py`, `src/services/extensions.py`, `src/services/connections.py`, extension parts of `src/services/app_config.py`, `src/_fixtures/reference_extension_server.py`, wiring in `src/run.py`; `src/service_catalog.py` imports `_origin` from `services/connections.py` | The proxy itself |
| Armory Admin | `views/ConnectionsView.vue` and test, `api/ConnectionsClient.ts`, `router/index.ts` (route `/connections`, alias `/extensions`), `router/pages.ts`, `router/guard.test.ts` (uses `/connections` as the home path) | The page |
| Policy | `libs/citadel_auth/citadel_auth/policy.py`: Armory accepts `/extensions` and `/connections` from Portcullis | Only these routes use them |

Legion's `mcp_upstream.list_tools` has a branch for "Armory-proxied tools require an enabled extension". It stays: with the proxy gone, no such tool exists, so the branch is inert (listed as a follow-up).

---

### Task 1: Ember drops the shared extension list

**Files:**
- Delete: `apps/ember/src/features/capabilities/api/ExtensionsClient.ts`
- Modify: `apps/ember/src/features/capabilities/views/CapabilitiesView.vue`, `utils/capabilityGroups.ts`, `apps/ember/src/features/chat/stores/chat.ts`, `features/chat/components/ChatSettingsMenu.vue`, `features/chat/views/ChatView.vue`, and every test that names `extensionsClient`, shared `ExtensionInfo` fixtures or the "Extensions:" menu line
- Test: `apps/ember/src/features/capabilities/noSharedExtensions.test.ts` (create)

**Interfaces:**
- Consumes: the private extension store and client (unchanged).
- Produces: no request to `/api/extensions`; no `extensionsClient`; the chat store's `enabledExtensions` is gone (Portcullis fills `extension_ids` itself, Task 2); the Capabilities page's "Extensions" tab lists only private extensions; the ability to add a private extension stays.

- [ ] **Step 1: List every use.** `git grep -n -E "extensionsClient|ExtensionInfo|enabledExtensions|enabled-extensions|extensionGroups|inExtensionNamespace|api/extensions" -- apps/ember/src`. Decide per hit: shared-only code goes; code that also serves private extensions or built-in tools stays. `EXTENSION_SEPARATOR` and `slashCommands.ts` keep working with an empty enabled list; if `enabledExtensions` is removed, remove its parameter chain in `slashCommands.ts` and `toolCommands.ts` only where the parameter has no other caller, else pass `[]`. Keep the diff small.

- [ ] **Step 2: Write the failing test**

```ts
// apps/ember/src/features/capabilities/noSharedExtensions.test.ts
import { describe, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import * as http from "@/utils/server";

// Copy the mount helper (router, pinia, stubs) from CapabilitiesView.test.ts; the names below stand for it.
import { mountCapabilities } from "./views/capabilitiesTestMount";

describe("shared extensions are gone from Ember", () => {
  it("never asks for /api/extensions", async () => {
    const calls: string[] = [];
    vi.spyOn(http, "apiRequest").mockImplementation(async (_method: string, path: string) => {
      calls.push(path);
      return [] as never;
    });
    mountCapabilities();
    await flushPromises();
    expect(calls.some((path) => path.startsWith("/api/extensions"))).toBe(false);
  });
});
```

If `CapabilitiesView.test.ts` has no reusable mount helper, build the mount inline from its first test; keep the behaviour statement. `apiRequest` may live in another module than `@/utils/server`: spy on the module that `ExtensionsClient.ts` imports it from (`git grep -n "apiRequest" -- apps/ember/src/features/capabilities/api`).

- [ ] **Step 3: Run it; see it fail** (`/api/extensions` is requested). `pnpm exec vitest run src/features/capabilities/noSharedExtensions.test.ts` from `apps/ember`.

- [ ] **Step 4: Remove.** Delete `ExtensionsClient.ts`; in `CapabilitiesView.vue` drop the `extensions` ref, the `extensionsClient.list()` call, the shared rows and the shared error text; in `capabilityGroups.ts` drop `extensionGroups` and its helpers if only the shared list used them; in `chat.ts` drop the refresh that calls `extensionsClient.list()` and the `enabledExtensions` ref and return entry; in `ChatSettingsMenu.vue` and `ChatView.vue` drop the prop and the "Extensions: ..." line. Update the tests that named them (delete shared-extension cases; keep every private-extension case).

- [ ] **Step 5: Run the touched tests and the type check.** The new test, `CapabilitiesView.test.ts`, `CapabilitiesWorkspace.test.ts`, `capabilityGroups.test.ts`, `ChatSettingsMenu` and chat-store tests that the grep in step 1 lists, then `pnpm exec vue-tsc -b`. Expected: pass.

---

### Task 2: Portcullis stops proxying extensions and connections

**Files:**
- Modify: `apps/portcullis/src/routes/server_info.py` (remove the three `/extensions` routes and now-unused schemas and imports), `apps/portcullis/src/services/mcp_server_info.py` (remove `extensions()`, `add_extension()`, `remove_extension()`), `apps/portcullis/src/routes/chats.py` (the `extension_ids` block near line 549), `apps/portcullis/src/routes/connections.py` (remove the `/admin/connections` routes; keep `readiness()` and `GET /api/connection-status`), `apps/portcullis/README.md`
- Modify (tests): the tests that call the removed routes or fake `info.extensions` (`git grep -l -E "/api/extensions|/admin/connections|\.extensions\(|add_extension|remove_extension" -- apps/portcullis/tests`)
- Test: `apps/portcullis/tests/test_extension_proxy_removed.py` (create)

**Interfaces:**
- Consumes: Task 1 (Ember no longer calls `/api/extensions`).
- Produces: `GET/POST/DELETE /api/extensions...` and `/api/admin/connections...` answer `404`; the trusted block sent to Stronghold carries `extension_ids: []` for every turn; `McpServerInfo` has no extension methods.

- [ ] **Step 1: List every use.** The grep above plus `git grep -n "extension_ids\|info.extensions" -- apps/portcullis/src`. Read `chats.py` around the `extension_ids` lines: the try/except around `info.extensions(account)` goes, and `extension_ids = []` stays as the value sent.

- [ ] **Step 2: Write the failing tests**

```python
# apps/portcullis/tests/test_extension_proxy_removed.py
import pytest

from src.services.mcp_server_info import McpServerInfo

# `client` and `login_admin`: the fixtures the other route tests use (tests/test_server_info.py).


@pytest.mark.parametrize("method, path", [
    ("GET", "/api/extensions"), ("POST", "/api/extensions"), ("DELETE", "/api/extensions/x"),
    ("GET", "/api/admin/connections"), ("PUT", "/api/admin/connections/bard"), ("DELETE", "/api/admin/connections/x"),
])
def test_the_extension_and_connection_proxy_routes_are_gone(client, method, path):
    login_admin(client)
    assert client.request(method, path, json={}).status_code == 404


def test_the_server_info_service_has_no_extension_methods():
    assert not hasattr(McpServerInfo, "extensions")
    assert not hasattr(McpServerInfo, "add_extension")
    assert not hasattr(McpServerInfo, "remove_extension")


def test_connection_status_still_works(client):
    login_admin(client)
    assert client.get("/api/connection-status").status_code in (200, 503)
```

Add one chat test beside the existing turn-start tests: the trusted block's `extension_ids` equals `[]` (copy how the nearest existing test reads the forwarded turn body). If an existing test asserts a non-empty `extension_ids` from a fake Armory list, change it to `[]`.

- [ ] **Step 3: Run them; see them fail.** `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_extension_proxy_removed.py` from `apps/portcullis`.

- [ ] **Step 4: Remove.** Routes, service methods, the `extension_ids` lookup and the dead schemas and imports they leave. Update the README's route table (drop the rows) and the Armory proxy sentence.

- [ ] **Step 5: Run the touched tests.** The new file, `test_server_info.py`, `test_connections.py` (or the file the grep names), the chat test file with the turn-start tests, and `test_user_extensions*.py` (private extensions must still pass). Expected: pass; the Portcullis suite has 2 known failures elsewhere (`test_secret_box.py`, `test_traffic.py`), which are not run here.

---

### Task 3: Armory removes the proxy and the connection records code

**Files:**
- Delete: `apps/armory/src/extension_routes.py`, `src/connection_admin.py`, `src/services/extensions.py`, `src/services/connections.py`, `src/_fixtures/reference_extension_server.py` (and `src/_fixtures/` if it holds nothing else), `apps/armory/tests/test_extensions.py`, `tests/test_extension_routes.py`, `tests/test_connection_admin.py`, and any other test that imports a deleted module
- Modify: `apps/armory/src/run.py`, `src/service_catalog.py` (take `_origin` over), `src/services/app_config.py` (remove the extension parts, keep the capability toggles and settings loaders), `src/capabilities/README.md`, `src/README.md`, `src/services/README.md`, `apps/armory/README.md`, `apps/armory/docs/settings.md`
- Test: `apps/armory/tests/test_capabilities_removed.py` (extend)

**Interfaces:**
- Consumes: Tasks 1 and 2 (nothing calls Armory `/extensions` or `/admin/connections`).
- Produces: Armory registers no `/extensions`, `/admin/connections` or proxied extension tools; `run.py` starts no extension task and shuts none down; `service_catalog.py` has its own `_origin` with the same behaviour.

- [ ] **Step 1: List every use.** `git grep -n -E "services import .*(extensions|connections)|services\.(extensions|connections)|extension_routes|connection_admin|ExtensionConfig|load_extension|save_extension|delete_extension|ConnectionStore|extension_entry|_origin" -- apps/armory ':!*/citadel_auth/*'`. Check `conftest.py` (the fixture list that monkeypatches `src.services.extensions.keyring`) and any test that uses `ExtensionConfig`. Read `_origin` in `connections.py` and copy it unchanged into `service_catalog.py`. Check `run.py`: remove `install_extensions(...)`, its task, `shutdown_extensions()`, `install_extension_routes`, `install_connection_admin`, `ConnectionStore`, and the `httpx.AsyncClient` block only if nothing else in `run.py` uses the client.

- [ ] **Step 2: Write the failing tests** (append to `tests/test_capabilities_removed.py`; keep its imports)

```python
@pytest.mark.parametrize("module", [
    "src.extension_routes", "src.connection_admin", "src.services.extensions", "src.services.connections",
])
def test_the_extension_proxy_modules_cannot_be_imported(module):
    assert importlib.util.find_spec(module) is None


def test_the_service_catalog_still_derives_origins():
    from src.service_catalog import _origin

    assert _origin("http://armory:29603/mcp").startswith("http://armory:29603")
```

Adjust the second test to the behaviour `_origin` really has (read its body in step 1); the point is that the helper survived the move. Rename or drop it if `_origin` turns out to be unused after the move (then remove the import from `service_catalog.py` instead).

- [ ] **Step 3: Run them; see them fail.** `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_capabilities_removed.py` from `apps/armory`.

- [ ] **Step 4: Remove.** Callers first (`run.py` wiring), then `app_config.py`'s extension parts, then the modules and tests. Boot-check by import only: `.venv\Scripts\python.exe -c "import src.run, src.server"` from `apps/armory` (no service start). Update the READMEs and `docs/settings.md` (drop the Connections row and extension text; the `extensions` and `connections` tables in `settings.db` stay and are mentioned as unused).

- [ ] **Step 5: Run the touched tests.** `tests/test_capabilities_removed.py`, `tests/test_environment_settings.py`, `tests/test_read_only_declarations.py`, the service-catalog test (`git grep -l service_catalog -- tests`), and the app-config tests (`git grep -l app_config -- tests`). Expected: pass.

---

### Task 4: Armory Admin drops the Connections page

**Files:**
- Delete: `apps/armory_admin/src/views/ConnectionsView.vue`, `ConnectionsView.test.ts`, `apps/armory_admin/src/api/ConnectionsClient.ts`
- Modify: `apps/armory_admin/src/router/index.ts` (route `/connections` with alias `/extensions`), `router/pages.ts`, `router/guard.test.ts` (its home path), `router/pages.test.ts`, `apps/armory_admin/README.md`
- Test: `apps/armory_admin/src/router/pages.test.ts` (extend)

**Interfaces:**
- Consumes: Task 3 (Armory has no `/admin/connections`).
- Produces: no `/connections` or `/extensions` route and no Connections nav entry; the guard's default landing page is the first remaining page.

- [ ] **Step 1: List every use.** `git grep -n -i -E "connections|ConnectionsClient|/extensions" -- apps/armory_admin/src apps/armory_admin/README.md`. Find where the guard and the nav pick a home page; after removal it must pick an existing route (Capabilities).

- [ ] **Step 2: Write the failing test** (replace the first test in `pages.test.ts`)

```ts
it("has no Connections page any more", () => {
  expect(ARMORY_PAGES.map((page) => page.to)).not.toContain("/connections");
  expect(ARMORY_PAGES.map((page) => page.to)).not.toContain("/brain");
  expect(router.hasRoute("connections")).toBe(false);
  expect(router.resolve("/extensions").matched).toHaveLength(0);
});
```

- [ ] **Step 3: Run it; see it fail.** `pnpm exec vitest run src/router/pages.test.ts` from `apps/armory_admin`.

- [ ] **Step 4: Remove** the route, nav entry, view, client and tests; change `guard.test.ts`'s `{ path: "/connections" }` home to the Capabilities path; update the README's page list.

- [ ] **Step 5: Run `pnpm exec vitest run src/router`, then `pnpm exec vue-tsc -b` and `pnpm exec vite build`.** Expected: pass.

---

### Task 5: Auth policy, docs and the final check

**Files:**
- Modify: `libs/citadel_auth/citadel_auth/policy.py` (Armory accepts from Portcullis: drop `/extensions` and `/connections`) and `libs/citadel_auth/tests/test_auth.py`; run the sync script
- Modify: the roadmap row 22c ("Built" after the merge; leave the row text)

**Interfaces:**
- Consumes: Tasks 2 to 4.
- Produces: Portcullis may no longer call Armory at `/extensions` or `/connections`.

- [ ] **Step 1: Prove both paths dead.** `git grep -n -E "\"/extensions|'/extensions|\"/connections|'/connections" -- apps/portcullis/src apps/armory/src ':!*/citadel_auth/*'` must show no call from Portcullis to Armory and no Armory route. If a live user remains, keep that path and list it under "Findings".

- [ ] **Step 2: Write the failing test** (append to `libs/citadel_auth/tests/test_auth.py`, using its `allowed` import)

```python
@pytest.mark.parametrize("path", ["/extensions", "/extensions/x", "/connections", "/connections/x"])
def test_portcullis_may_not_call_armory_for_the_removed_proxy_routes(path):
    assert not allowed("armory", "portcullis", path)


def test_portcullis_may_still_call_armory_for_its_other_routes():
    assert allowed("armory", "portcullis", "/capabilities") and allowed("armory", "portcullis", "/commands/help")
```

- [ ] **Step 3: Run it; see it fail.** From `libs/citadel_auth`: `python -m pytest -q -p no:cacheprovider tests/test_auth.py` with an interpreter that has the library's test dependencies (the Armory `.venv` python works).

- [ ] **Step 4: Edit `policy.py`, run `python scripts/sync_citadel_auth.py`, then `python scripts/sync_citadel_auth.py --check` (must exit 0).** Run the new tests and any older policy test that listed these paths as allowed; change an old test only if it asserted the removed path was allowed.

- [ ] **Step 5: Sweep and report.** `git grep -n -i -E "extension_routes|connection_admin|services\.extensions|services\.connections|extensionsClient|ConnectionsClient|/api/extensions|/admin/connections" -- apps libs scripts docs ':!docs/superpowers' ':!*/node_modules/*' ':!*/.venv/*' ':!apps/ember_web'`. Expect no hits except tests that pin the removal. List each remaining hit with its reason. Run `git diff --check`.

## Self-review

- **Spec coverage:** Armory "Not: connection records, extensions proxy" (Tasks 3, 4); Portcullis pass-through removed (Task 2); Ember follows (Task 1); the policy matches the code (Task 5). Stronghold's private extensions and Legion's connections are untouched.
- **Order check:** Ember stops calling, then Portcullis stops proxying and stops reading Armory's list for `extension_ids`, then Armory removes the routes and modules, then the admin page, then the policy.
- **Placeholders:** the fixture and helper names marked "copy from" or "use the real" live in test files this plan did not read; each says where to find them.
- **Risk:** the biggest is Task 1's chain around `enabledExtensions`. If a chat feature other than shared extensions uses it, the executor keeps that part and reports it. Shared extensions Armory holds today stop reaching Legion: that is the decision stated above.

## Open questions for the user

1. Is it right that shared extensions leave Ember entirely, with admins re-adding the ones they still want as Legion connections? The alternative is a read-only "Connections" list in Ember fed by Legion, which needs a new Portcullis route and is not in this plan.
2. Old shared extension records stay in Armory's `settings.db`, unused. Say if a prune script is wanted.
3. `enabled_extensions` and `extension_ids` stay as an inert empty list across Portcullis, Stronghold and Legion, and `mcp_upstream` keeps its "Armory-proxied tools" branch. A later small plan can remove them; the plan leaves them to keep this one inside three services.
