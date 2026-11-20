# Plan 17: Treasury Admin page for outside services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An administrator sees every outside service group in Treasury Admin, renames a group, and deletes an origin or a group after a confirmation that lists the services using it.

**Architecture:** Portcullis forwards four new routes under `/api/admin/treasury/outside` to Treasury's `/admin/outside` routes (Plan 16) behind `settings.manage`, logging actions without addresses. Treasury Admin gets a client section and one new page, "Outside services". Adding groups stays in the Legion and Stronghold connection forms (Plans 18 and 19); this page only renames and deletes.

**Tech Stack:** Python 3.12+, FastAPI, pytest, uv; Vue 3 + TypeScript, vitest, pnpm.

**Spec:** `docs/superpowers/specs/2026-11-20-service-scopes-design.md`, section "Outside services and the catalog (Treasury)". Depends on Plan 16 (merged): `docs/superpowers/plans/2026-11-20-plan-16-outside-service-catalog.md`.

**Status:** Complete on `plan-17-outside-admin`.

## Baseline

At `8d432e3d` before implementation:

- Portcullis: 961 passed, 2 failed in 12m 23s with `uv run pytest -q -p no:cacheprovider` and a disposable pytest temp directory. Both known failures reject `http://127.0.0.1:0`.
  - `tests/test_secret_box.py::test_an_invalid_key_in_env_stops_startup`
  - `tests/test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`
- Treasury Admin: `pnpm exec vue-tsc -b` passed. `pnpm exec vitest run` passed 41 tests across 10 files.

## Global Constraints

- Only Treasury admin deletes origins and groups and renames groups; consumers never do.
- The route needs permission `settings.manage` (same as the other Treasury admin routes). No new permission.
- The audit log never contains an address: log the service id or origin id only.
- Treasury refuses a delete of an entry in use without `confirm=true`. The page always asks the user first, listing `used_by`, and then sends `confirm=true`.
- Treasury stores no tokens; nothing on this page shows or edits a token.
- UI: read `.agents/skills/ember-frontend-design/SKILL.md` and `ember-design-system` before changing Treasury Admin; reuse `PageLayout`, `ConfirmModal`, the existing table and form styles; no new radius values (the radius test in `src/radiusScale.test.ts` must pass); never add reduced-motion code.
- Python through `uv`, JS through `pnpm`. Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## File structure

| File | Responsibility |
|---|---|
| `apps/portcullis/src/routes/admin_treasury.py` (modify) | Four proxy routes |
| `apps/portcullis/tests/conftest.py` (modify) | Fake gateway answers `/admin/outside` |
| `apps/portcullis/tests/test_admin_treasury.py` (modify) | Route tests |
| `apps/treasury_admin/src/api/TreasuryAdminClient.ts` (modify) | Types and four client methods |
| `apps/treasury_admin/src/views/OutsideView.vue` (create) | The page |
| `apps/treasury_admin/src/views/OutsideView.test.ts` (create) | Page tests |
| `apps/treasury_admin/src/router/index.ts`, `pages.ts` (modify) | Route and nav entry |
| `apps/treasury_admin/README.md`, `apps/portcullis/README.md` (modify) | One line each |

### Task 1: Portcullis proxy routes

**Files:**
- Modify: `apps/portcullis/src/routes/admin_treasury.py` (append after `delete_service`)
- Modify: `apps/portcullis/tests/conftest.py` (`FakeDbGateway.admin`, line ~207)
- Test: `apps/portcullis/tests/test_admin_treasury.py`

**Interfaces:**
- Consumes (Treasury, Plan 16): `GET /admin/outside` returns `{"groups": [{"service_id","name","origins":[{"origin_id","origin"}],"used_by":[str]}]}`; `PATCH /admin/outside/{service_id}` body `{"name"}` returns one group; `DELETE /admin/outside/origins/{origin_id}[?confirm=true]` and `DELETE /admin/outside/{service_id}[?confirm=true]` return the groups view.
- Produces (Portcullis): `GET /api/admin/treasury/outside`; `PATCH /api/admin/treasury/outside/{service_id}` body `{"name": str}`; `DELETE /api/admin/treasury/outside/origins/{origin_id}?confirm=true|false`; `DELETE /api/admin/treasury/outside/{service_id}?confirm=true|false`. Same responses as Treasury. A Treasury 4xx comes back as 400 with Treasury's message (existing `_admin` behaviour); an outage is 502.

- [x] **Step 1: Teach the fake gateway the new paths**

In `apps/portcullis/tests/conftest.py`, in `FakeDbGateway.admin`, add before the final `return`:

```python
        if path.startswith("/admin/outside"):
            return {"groups": []}
```

- [x] **Step 2: Write the failing tests** (append to `test_admin_treasury.py`; it already imports `as_admin`, `make_member`, `login`)

```python
def test_outside_routes_forward_rename_and_deletes_and_audit_without_addresses(client, db_gateway):
    admin = as_admin(client)
    sid, oid = "a" * 32, "b" * 32
    assert admin.get("/api/admin/treasury/outside").json() == {"groups": []}
    assert admin.patch(f"/api/admin/treasury/outside/{sid}", json={"name": "speech"}).status_code == 200
    assert admin.delete(f"/api/admin/treasury/outside/origins/{oid}", params={"confirm": "true"}).status_code == 200
    assert admin.delete(f"/api/admin/treasury/outside/{sid}", params={"confirm": "true"}).status_code == 200
    assert admin.delete(f"/api/admin/treasury/outside/{sid}").status_code == 200
    assert db_gateway.admin_calls == [
        ("GET", "/admin/outside", None),
        ("PATCH", f"/admin/outside/{sid}", {"name": "speech"}),
        ("DELETE", f"/admin/outside/origins/{oid}?confirm=true", None),
        ("DELETE", f"/admin/outside/{sid}?confirm=true", None),
        ("DELETE", f"/admin/outside/{sid}", None),
    ]
    uid = admin.get("/api/auth/me").json()["id"]
    logged = " ".join(entry["message"] for entry in admin.get("/api/logs/action", params={"actor": uid}).json())
    assert f"Renamed outside service '{sid}'" in logged
    assert f"Removed outside origin '{oid}'" in logged
    assert f"Removed outside service '{sid}'" in logged
    assert "speech" not in logged and "http" not in logged


def test_outside_routes_need_settings_manage(client, email, db_gateway):
    sid = "a" * 32
    assert client.get("/api/admin/treasury/outside").status_code == 401
    make_member(client, email, "alice")
    login(client, "alice")
    assert client.get("/api/admin/treasury/outside").status_code == 403
    assert client.patch(f"/api/admin/treasury/outside/{sid}", json={"name": "x"}).status_code == 403
    assert client.delete(f"/api/admin/treasury/outside/{sid}").status_code == 403
    assert client.delete(f"/api/admin/treasury/outside/origins/{sid}").status_code == 403
    assert db_gateway.admin_calls == []


def test_outside_routes_report_refusals_and_outages(client, db_gateway):
    from src.services.db_gateway import DbGatewayUnavailable
    admin = as_admin(client)
    db_gateway.admin_refusal = "the name 'armory' is the name of a Citadel service"
    refused = admin.patch(f"/api/admin/treasury/outside/{'a' * 32}", json={"name": "armory"})
    assert (refused.status_code, refused.json()["detail"]) == (400, db_gateway.admin_refusal)

    async def down(*args, **kwargs):
        raise DbGatewayUnavailable("down")

    client.app.state.db_gateway.admin = down
    assert admin.get("/api/admin/treasury/outside").status_code == 502
```

- [x] **Step 3: Run to verify failure**

Run (from `apps/portcullis`): `uv run pytest tests/test_admin_treasury.py -q -p no:cacheprovider -k outside`
Expected: FAIL (404 on the new routes; the 401 assertion may already pass).

- [x] **Step 4: Implement** (append to `admin_treasury.py`)

```python
@router.get("/outside")
async def outside(_account: Account = Depends(require_manage), store: Any = Depends(get_db_gateway)) -> Any:
    """The outside service groups, their origins and which Citadel services use each."""
    return await _admin(store, "GET", "/admin/outside")


@router.patch("/outside/{service_id}")
async def rename_outside(
    service_id: str, spec: dict[str, str], account: Account = Depends(require_manage),
    store: Any = Depends(get_db_gateway), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Rename a group; its id, and so every consumer's reference, stays the same."""
    result = await _admin(store, "PATCH", f"/admin/outside/{quote(service_id, safe='')}", spec)
    await logs.action(account, "treasury.outside_rename", f"Renamed outside service '{service_id}'")
    return result


@router.delete("/outside/origins/{origin_id}")
async def delete_outside_origin(
    origin_id: str, confirm: bool = False, account: Account = Depends(require_manage),
    store: Any = Depends(get_db_gateway), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Remove one origin. Treasury refuses (400) while a service uses the group, unless confirm=true."""
    suffix = "?confirm=true" if confirm else ""
    result = await _admin(store, "DELETE", f"/admin/outside/origins/{quote(origin_id, safe='')}{suffix}")
    await logs.action(account, "treasury.outside_origin_delete", f"Removed outside origin '{origin_id}'")
    return result


@router.delete("/outside/{service_id}")
async def delete_outside_group(
    service_id: str, confirm: bool = False, account: Account = Depends(require_manage),
    store: Any = Depends(get_db_gateway), logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Remove a group with its origins. Treasury refuses (400) while a service uses it, unless confirm=true."""
    suffix = "?confirm=true" if confirm else ""
    result = await _admin(store, "DELETE", f"/admin/outside/{quote(service_id, safe='')}{suffix}")
    await logs.action(account, "treasury.outside_delete", f"Removed outside service '{service_id}'")
    return result
```

Note: `"http" not in logged` in the first test assumes no other action-log entry from `as_admin` contains "http". If it does, assert that the origin string `"bard"`-style addresses are absent by logging only ids (already true) and narrow the assertion to the entries that start with "Renamed outside" or "Removed outside".

- [x] **Step 5: Run to verify pass, then the module and a full Portcullis run**

Run: `uv run pytest tests/test_admin_treasury.py -q -p no:cacheprovider` then, in the background writing to a file, `uv run pytest -q -p no:cacheprovider` (about 10 minutes).
Expected: PASS; the full run keeps only the two known failures `tests/test_secret_box.py::test_an_invalid_key_in_env_stops_startup` and `tests/test_traffic.py::test_the_default_recorder_saves_to_the_database_on_shutdown`.

- [x] **Step 6: Commit**

```bash
git add apps/portcullis/src/routes/admin_treasury.py apps/portcullis/tests/conftest.py apps/portcullis/tests/test_admin_treasury.py
git commit -m "feat(portcullis): pass the outside-service catalog to Treasury Admin"
```

### Task 2: Treasury Admin client and page

**Files:**
- Modify: `apps/treasury_admin/src/api/TreasuryAdminClient.ts`
- Create: `apps/treasury_admin/src/views/OutsideView.vue`, `apps/treasury_admin/src/views/OutsideView.test.ts`
- Modify: `apps/treasury_admin/src/router/index.ts`, `apps/treasury_admin/src/router/pages.ts`

**Interfaces:**
- Consumes: the Portcullis routes of Task 1.
- Produces (client): types `OutsideOrigin { origin_id: string; origin: string }`, `OutsideGroup { service_id: string; name: string; origins: OutsideOrigin[]; used_by: string[] }`, `OutsideView { groups: OutsideGroup[] }`; methods `getOutside()`, `renameOutside(serviceId, name) -> OutsideGroup`, `deleteOutsideOrigin(originId) -> OutsideView`, `deleteOutsideGroup(serviceId) -> OutsideView`. Both delete methods always send `confirm=true`; the page asks first.

- [x] **Step 1: Write the failing page tests**

```ts
// apps/treasury_admin/src/views/OutsideView.test.ts
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { treasuryAdminClient } from "../api/TreasuryAdminClient";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import OutsideView from "./OutsideView.vue";

const view = { groups: [
  { service_id: "a".repeat(32), name: "bard", used_by: ["legion", "stronghold"],
    origins: [{ origin_id: "b".repeat(32), origin: "http://bard:29400" }, { origin_id: "c".repeat(32), origin: "http://bard2:29400" }] },
  { service_id: "d".repeat(32), name: "lens", used_by: [], origins: [{ origin_id: "e".repeat(32), origin: "http://lens:29403" }] },
] };
beforeEach(() => vi.spyOn(treasuryAdminClient, "getOutside").mockResolvedValue(view));
afterEach(() => vi.restoreAllMocks());

it("lists groups with their origins and users", async () => {
  const wrapper = mount(OutsideView);
  await flushPromises();
  expect(wrapper.findAll("tbody tr")).toHaveLength(2);
  const bard = wrapper.get('[data-test="group-bard"]').text();
  expect(bard).toContain("http://bard:29400");
  expect(bard).toContain("http://bard2:29400");
  expect(bard).toContain("legion");
  expect(wrapper.get('[data-test="group-lens"]').text()).toContain("Not used");
  wrapper.unmount();
});

it("renames a group and reloads", async () => {
  const rename = vi.spyOn(treasuryAdminClient, "renameOutside").mockResolvedValue(view.groups[0]);
  const wrapper = mount(OutsideView);
  await flushPromises();
  await wrapper.get('[data-test="group-bard"] input').setValue("speech");
  await wrapper.get('[data-test="group-bard"] form').trigger("submit");
  await flushPromises();
  expect(rename).toHaveBeenCalledWith("a".repeat(32), "speech");
  expect(treasuryAdminClient.getOutside).toHaveBeenCalledTimes(2);
  wrapper.unmount();
});

it("keeps the draft and shows Treasury's refusal on a bad rename", async () => {
  vi.spyOn(treasuryAdminClient, "renameOutside").mockRejectedValue(new Error("the name 'armory' is the name of a Citadel service"));
  const wrapper = mount(OutsideView);
  await flushPromises();
  await wrapper.get('[data-test="group-bard"] input').setValue("armory");
  await wrapper.get('[data-test="group-bard"] form').trigger("submit");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("Citadel service");
  expect((wrapper.get('[data-test="group-bard"] input').element as HTMLInputElement).value).toBe("armory");
  wrapper.unmount();
});

it("asks first, naming the users, then deletes a group", async () => {
  const remove = vi.spyOn(treasuryAdminClient, "deleteOutsideGroup").mockResolvedValue({ groups: [view.groups[1]] });
  const wrapper = mount(OutsideView);
  await flushPromises();
  await wrapper.get('[data-test="group-bard"] [data-test="delete-group"]').trigger("click");
  const modal = wrapper.getComponent(ConfirmModal);
  expect(modal.props("open")).toBe(true);
  expect(modal.props("message")).toContain("legion, stronghold");
  expect(remove).not.toHaveBeenCalled();
  modal.vm.$emit("confirm");
  await flushPromises();
  expect(remove).toHaveBeenCalledWith("a".repeat(32));
  expect(wrapper.findAll("tbody tr")).toHaveLength(1);
  wrapper.unmount();
});

it("deletes one origin after confirmation", async () => {
  const remove = vi.spyOn(treasuryAdminClient, "deleteOutsideOrigin").mockResolvedValue(view);
  const wrapper = mount(OutsideView);
  await flushPromises();
  await wrapper.get('[data-test="group-bard"] [data-test="delete-origin-' + "c".repeat(32) + '"]').trigger("click");
  wrapper.getComponent(ConfirmModal).vm.$emit("confirm");
  await flushPromises();
  expect(remove).toHaveBeenCalledWith("c".repeat(32));
  wrapper.unmount();
});
```

- [x] **Step 2: Run to verify failure**

Run (from `apps/treasury_admin`): `pnpm exec vitest run src/views/OutsideView.test.ts`
Expected: FAIL, cannot resolve `./OutsideView.vue`.

- [x] **Step 3: Add the client types and methods** (in `TreasuryAdminClient.ts`, after `ServicesView`)

```ts
export interface OutsideOrigin { origin_id: string; origin: string; }

/** An outside service: its id never changes, the name is only a label. Addresses only, never a token. */
export interface OutsideGroup {
  service_id: string;
  name: string;
  origins: OutsideOrigin[];
  /** The Citadel services that use it. */
  used_by: string[];
}

export interface OutsideView { groups: OutsideGroup[]; }
```

and inside `treasuryAdminClient`:

```ts
  getOutside: () => apiRequest<OutsideView>("GET", "/api/admin/treasury/outside"),
  renameOutside: (serviceId: string, name: string) =>
    apiRequest<OutsideGroup>("PATCH", `/api/admin/treasury/outside/${encodeURIComponent(serviceId)}`, { name }),
  /** The page asks the user first, so these always confirm. */
  deleteOutsideOrigin: (originId: string) =>
    apiRequest<OutsideView>("DELETE", `/api/admin/treasury/outside/origins/${encodeURIComponent(originId)}?confirm=true`),
  deleteOutsideGroup: (serviceId: string) =>
    apiRequest<OutsideView>("DELETE", `/api/admin/treasury/outside/${encodeURIComponent(serviceId)}?confirm=true`),
```

- [x] **Step 4: Write the page**

```vue
<!-- apps/treasury_admin/src/views/OutsideView.vue -->
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { treasuryAdminClient, type OutsideGroup, type OutsideOrigin, type OutsideView } from "../api/TreasuryAdminClient";
import ConfirmModal from "../components/admin/ConfirmModal.vue";
import PageLayout from "../components/PageLayout.vue";
import { errorMessage } from "../utils/errors";
import "../components/infoPage.css";

type Target = { group: OutsideGroup; origin?: OutsideOrigin };

const { getOutside, renameOutside, deleteOutsideOrigin, deleteOutsideGroup } = treasuryAdminClient;
const groups = ref<OutsideGroup[]>([]);
const drafts = ref<Record<string, string>>({});
const loading = ref(true);
const busy = ref(false);
const error = ref("");
const target = ref<Target | null>(null);

function applyView(next: OutsideView) {
  groups.value = next.groups;
  drafts.value = Object.fromEntries(next.groups.map((group) => [group.service_id, group.name]));
}

onMounted(async () => {
  try { applyView(await getOutside()); }
  catch (err) { error.value = errorMessage(err); }
  finally { loading.value = false; }
});

async function rename(group: OutsideGroup) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    await renameOutside(group.service_id, String(drafts.value[group.service_id]).trim());
    applyView(await getOutside());
  } catch (err) { error.value = errorMessage(err); }
  finally { busy.value = false; }
}

const message = computed(() => {
  const current = target.value;
  if (!current) return "";
  const users = current.group.used_by.length
    ? ` ${current.group.used_by.join(", ")} use${current.group.used_by.length === 1 ? "s" : ""} it and will lose the connection.`
    : "";
  return current.origin
    ? `Remove the origin ${current.origin.origin} from ${current.group.name}?${users}`
    : `Remove ${current.group.name} and all its origins?${users}`;
});

async function remove() {
  const current = target.value;
  if (!current || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    applyView(current.origin ? await deleteOutsideOrigin(current.origin.origin_id) : await deleteOutsideGroup(current.group.service_id));
    target.value = null;
  } catch (err) { error.value = errorMessage(err); }
  finally { busy.value = false; }
}
</script>

<template>
  <PageLayout class="info-content outside" title="Outside services" description="Tool services and gateways that Citadel services call. Legion and Stronghold add an address when an administrator saves a connection; here you rename a group or remove what is no longer needed. Only addresses are kept here, never a token.">
    <p v-if="error" class="error" role="alert" id="outside-error">{{ error }}</p>
    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="!groups.length" class="muted">No outside services yet.</p>
    <div v-else class="table-scroll" role="region" aria-label="Outside services" tabindex="0">
      <table>
        <thead><tr><th>Name</th><th>Origins</th><th>Used by</th><th>Remove</th></tr></thead>
        <tbody>
          <tr v-for="group in groups" :key="group.service_id" :data-test="'group-' + group.name">
            <td>
              <form class="rename-form" @submit.prevent="rename(group)">
                <label :for="'name-' + group.service_id">Name of {{ group.name }}</label>
                <input :id="'name-' + group.service_id" v-model="drafts[group.service_id]" :disabled="busy" :aria-describedby="error ? 'outside-error' : undefined" autocomplete="off" spellcheck="false" />
                <button type="submit" class="primary" :disabled="busy || !String(drafts[group.service_id] ?? '').trim() || drafts[group.service_id] === group.name" :aria-busy="busy">Rename</button>
              </form>
            </td>
            <td>
              <ul class="origins">
                <li v-for="origin in group.origins" :key="origin.origin_id">
                  <code>{{ origin.origin }}</code>
                  <button type="button" class="chip" :data-test="'delete-origin-' + origin.origin_id" :disabled="busy" @click="target = { group, origin }">Remove origin</button>
                </li>
              </ul>
            </td>
            <td>{{ group.used_by.length ? group.used_by.join(", ") : "Not used" }}</td>
            <td><button type="button" class="chip" data-test="delete-group" :disabled="busy" @click="target = { group }">Remove service</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <ConfirmModal
      :open="target !== null"
      :title="target?.origin ? 'Remove origin' : 'Remove outside service'"
      :message="message"
      confirm-label="Remove"
      danger
      :busy="busy"
      @confirm="remove"
      @close="target = null"
    />
  </PageLayout>
</template>

<style scoped>
.table-scroll { overflow-x: auto; }
.rename-form { display: grid; gap: 8px; min-width: 200px; }
.rename-form label { font-size: 0.85em; color: var(--muted); }
.rename-form input { min-height: 44px; width: 100%; }
.origins { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.origins li { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
</style>
```

- [x] **Step 5: Add the route and the nav entry**

In `router/index.ts` add before the `/login` route:

```ts
    { path: "/outside", name: "outside", component: () => import("../views/OutsideView.vue"), meta: { permission: "settings.manage" } },
```

In `router/pages.ts` append to `TREASURY_PAGES`:

```ts
  { to: "/outside", label: "Outside services", icon: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18", "M3 12h18", "M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3"], permission: "settings.manage" },
```

(The icon is a globe: a circle, an equator and a meridian. Any 24x24 stroked paths from the existing icon style are fine.)

- [x] **Step 6: Run to verify pass, then the whole app**

Run: `pnpm exec vitest run src/views/OutsideView.test.ts` then `pnpm exec vue-tsc -b` then `pnpm exec vitest run`.
Expected: PASS everywhere. If `router/index.test.ts` or a nav test counts pages, update the expected count and the page list in that test (baseline at Plan 14: 41 tests).

- [x] **Step 7: Commit**

```bash
git add apps/treasury_admin
git commit -m "feat(treasury_admin): page to rename and remove outside services"
```

### Task 3: Docs and verification

- [x] **Step 1:** In `apps/treasury_admin/README.md` add the page to its page list ("Outside services: rename a group, remove an origin or a service; shows who uses each"). In `apps/portcullis/README.md` add the four routes to the Treasury admin routes list. Update the vault is not part of this task.
- [x] **Step 2:** Run the suites: Portcullis (background, to a file), Treasury Admin (`pnpm exec vue-tsc -b`, `pnpm exec vitest run`). Expected: only the two known Portcullis failures.
- [x] **Step 3:** Add a "Verification" section at the end of this plan file with the commands and counts, and any change found during work.
- [x] **Step 4:** Commit:

```bash
git add apps/treasury_admin/README.md apps/portcullis/README.md docs/superpowers/plans/2026-11-20-plan-17-outside-admin-page.md
git commit -m "docs: Treasury Admin outside-services page and its routes"
```

## Self-review notes
- Spec coverage for this slice: rename and delete only in Treasury admin (Tasks 1 and 2), `used_by` in the delete confirmation (Task 2 `message`), no tokens shown (global constraint; the page renders only names, origins and users), no addresses in the audit log (Task 1 test). The roadmap line said "and add"; this plan leaves adding to the consumer forms, as the spec says, so the page has no add form.
- Not verified without a browser: the page layout at phone width and the real Treasury round trip. Treasury's `used_by` comes from Plan 16; a service appears there only after it saved an origin through its own form (Plans 18 and 19), so until then every group shows "Not used".
- Names match across tasks: `getOutside`, `renameOutside`, `deleteOutsideOrigin`, `deleteOutsideGroup`, `OutsideGroup`, `OutsideOrigin`, `OutsideView`, routes `/api/admin/treasury/outside...`.


## Changes found during work

- The proxy validates the 32-character hexadecimal IDs produced by Treasury before forwarding or auditing a mutation. The rename forwards only the name. Tests cover malformed IDs and extra request fields.
- Vitest's DOM lacks the native dialog methods. The new tests use the same test-local shim as Connections and click the real ConfirmModal buttons.
- Refresh keeps unfinished edits in other rows. A successful rename remains visible if its reload fails. A failed delete closes the dialog and puts the error beside the attempted action, so the error stays visible in a scrolled catalog.
- The Portcullis README had no separate Treasury admin route list. The four routes were added to its API table.
- Windows loopback tests used disposable pytest directories. Each Portcullis run wrote to an ignored local log.
- Confirmation lists users from the loaded catalog snapshot. Usage changes in another service while the page is open can be newer than that snapshot.

## Verification

| Project | Command | Baseline | Plan 17 |
|---|---|---|---|
| Portcullis proxy | `uv run pytest tests/test_admin_treasury.py -q -p no:cacheprovider` | 9 existing tests | 13 passed |
| Portcullis full | `uv run pytest -q -p no:cacheprovider` | 961 passed, 2 failed | 965 passed and the same 2 failures in both full runs |
| Outside services view | `pnpm exec vitest run src/views/OutsideView.test.ts` | New suite | 8 passed |
| Treasury Admin full | `pnpm exec vitest run` | 41 passed | 49 passed, including the radius scale test |
| Treasury Admin type check | `pnpm exec vue-tsc -b` | Passed | Passed |

Portcullis's two failures match the baseline names and port-0 cause. Task 1 took 15m 15s and final verification took 14m 07s. Both runs used isolated pytest temporary directories.

Desktop and phone browser layout, a live Treasury round trip with a registered group, and Docker remain unverified.
