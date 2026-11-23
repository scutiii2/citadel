# Legion Admin redesign implementation plan

Implement the [specification](../specs/2026-11-23-legion-admin-redesign-design.md) using the [approved mockup](../../../apps/legion_admin/mockups/legion-redesign.html) and [frontend skill](../../../.agents/skills/ember-frontend-design/SKILL.md). One implementer can work through the tasks in order in the current checkout. Run each task's focused command once after its edits.

The Vue 3 and TypeScript app continues to use its Portcullis clients and permission guards. Extend the existing gateway document contract in Legion and Portcullis before wiring the new Connections UI. Keep the mockup available for visual comparison.

## 1. Production shell and shared presentation

**Files under `apps/legion_admin`.** `src/App.vue`, `src/components/LegionNav.vue`, and `src/style.css`. Add `src/components/LegionHeader.vue`, `src/components/admin/AdminSearch.vue`, and `src/components/admin/RecordDrawer.vue`.

- [x] Mount the full-width header only on the signed-in admin shell. Derive the displayed title from the active route and filter sidebar entries through the auth store. Preserve auth redirects and stored theme choices. Keep the MCP servers route available until Task 5 integrates its panel.
- [x] Move theme and logout into Profile. Populate Notifications from `agentsAdminClient.live()` for accounts with `agents.manage`. Treat denied or failed status loads as unavailable. Reuse route query `status=offline` for the roster link. Keep the current admin app URLs in the sidebar and the Help control in the header.
- [x] Build `AdminSearch` with a string `v-model` and accessible label. Build `RecordDrawer` on `BaseModal` side mode with header Edit/Expand/Close actions, a body slot, and a pinned footer slot. Keep the same drawer instance while resizing. Keep styling local to Legion and reuse existing token variables and `ConfirmModal`. Use shell-scoped `PageLayout` presentation for the single title, preserving its actions and toolbar slots. Clip hover and focus paint at rounded panel edges and keep table scroll containers local.
- [x] Add `src/components/admin/RecordDrawer.test.ts` for draft and body persistence across expand and shrink and single close requests. Cover nav, profile, and notification controls in `src/components/LegionHeader.test.ts` using mocked auth and live state. Inspect the shell in the browser at desktop and narrow widths.

Run from `apps/legion_admin`:

```powershell
pnpm exec vitest run src/components/LegionHeader.test.ts src/components/admin/RecordDrawer.test.ts src/radiusScale.test.ts
```

## 2. Agents roster and editor drawer

**Files under `apps/legion_admin`.** `src/views/AgentsAdminView.vue`, `src/components/admin/AgentForm.vue`, `src/components/admin/AgentAdminCard.vue`, and `src/components/admin/SharedPromptsModal.vue` as needed for the drawer content.

- [x] Build a searchable roster over the configured list and existing live data. Keep unknown status distinct from Offline, honor the `status=offline` link, and compute counts before text filtering. Use native row openers stretched across each row with visible keyboard focus. Place New agent and Shared prompts in the panel actions.
- [x] Reuse agent details and `AgentForm` fields in the drawer. Use the header pencil to enter edit mode. Put Save/Create and Cancel at the bottom and keep existing validation, prompt preview, shared prompts, configured roles, and routing controls. Gate writes with `ConfirmModal`; protect drafts on Cancel, Escape, backdrop, and Close. Keep existing reset, typed deletion, and entry-agent restrictions.
- [x] Extend `src/views/AgentsAdminView.test.ts` for filter counts and unknown status, drawer edit/confirmation, retained drafts after API rejection, and preserved create, reset, and removal paths.

Run from `apps/legion_admin`:

```powershell
pnpm exec vitest run src/views/AgentsAdminView.test.ts src/components/admin/SharedPromptsModal.test.ts
```

## 3. Legion gateway description persistence

**Files under `apps/legion`.** `src/runtime/gateway_settings.py`, `src/server.py` endpoint docs, and `tests/test_gateway_settings.py`.

- [x] Add `GatewaySettings.description: str = ""` so existing two-argument callers and older records work. Decode missing descriptions as empty. Extend `save()` to validate and merge `description`, retaining saved data for omitted fields. Use the current per-key Treasury record and validate before writing. Serialize the existing read/merge/write sequence per gateway key within the Legion admin process so overlapping partial writes there cannot overwrite each other. Keep cache update after successful persistence.
- [x] Expose description in `view()` with URL and token presence. Keep URL normalization, validate trimmed descriptions up to 500 characters and support empty-string clear. Preserve existing token secrecy and cache fallbacks.
- [x] Extend `tests/test_gateway_settings.py` for both keys, legacy records, description clearing, description-only and URL-only patches, conflicting or invalid writes, concurrent same-process patches, failure recovery, and no token echo.

Run from `apps/legion`:

```powershell
uv run pytest tests/test_gateway_settings.py -q
```

## 4. Portcullis gateway contract

**Files under `apps/portcullis`.** `src/routes/agent_admin.py`, `src/services/agent_admin.py` contract docs, `src/app.py` validation redaction, and `tests/test_agent_admin.py`.

- [x] Add optional description to `GatewaySettingsIn` on both existing routes. Keep `exclude_unset` and `exclude_none` semantics so older callers work and an empty description clears the saved value. Preserve `agents.manage` on reads and writes and audit field names only.
- [x] Extend the gateway route tests for description forwarding and clearing, refusal of oversized input, isolation between gateway routes, and response redaction. Keep existing permission checks. Remove raw inputs from gateway and MCP connection validation errors so rejected credentials stay write-only.

Run from `apps/portcullis`:

```powershell
uv run pytest tests/test_agent_admin.py -q -k 'gateway_settings or servers'
```

## 5. Unified Connections page

**Files under `apps/legion_admin`.** `src/views/ConnectionsView.vue`, `src/views/ServersView.vue`, `src/components/GatewayConnectionCard.vue`, `src/api/AgentsAdminClient.ts`, `src/router/index.ts`, and `src/router/pages.ts`.

- [x] Embed the existing server table and editor as a panel inside the Connections `PageLayout`. Give both panels independent local search and errors. Put transport-appropriate endpoints in the shared row presentation. Remove the standalone sidebar item and redirect `/servers` to `/connections#mcp-servers`, preserving the query string. Keep the `agents.manage` guard and scroll or focus the MCP section after it mounts.
- [x] Use drawers for gateway read/edit and MCP add/read/edit, reusing the existing field and API behavior. Extend `GatewaySettingsView` and request types with optional `description`. Submit changed gateway fields only, with blank untouched token excluded and explicit token removal preserved. Keep failed drafts open and report the existing apply timing.
- [x] Preserve MCP catalog lookup, ordered origins, overrides, direct HTTP, stdio, add/remove, and permission checks. Ignore late lookup replies after a row changes. Keep unresolved origin rows visible and explain how to repair them before save. Keep identity and order for resolved origins on a description-only edit. Preserve server and gateway credentials as write-only fields.
- [x] Extend `src/views/ServersView.test.ts` and `src/components/GatewayConnectionCard.test.ts` around the new presentation. Add `src/views/ConnectionsView.test.ts` for both panels, isolated search, and partial load failure. Keep existing transport, token preservation, and rejected-write coverage. Extend `src/router/index.test.ts` to verify the old URL and the permission guard. Inspect the last row's hover and focus corners in Light and Dark.

Run from `apps/legion_admin`:

```powershell
pnpm exec vitest run src/views/ConnectionsView.test.ts src/views/ServersView.test.ts src/components/GatewayConnectionCard.test.ts src/router/index.test.ts
```

## 6. Tuning panel and draft actions

**Files under `apps/legion_admin`.** `src/views/TuningAdminView.vue` and `src/views/TuningAdminView.test.ts`.

- [x] Wrap the existing setting groups in a searchable panel. Keep setting groups, ranges, enum and switch semantics, overrides, per-field reset, and file defaults. Filter rendered rows locally without removing their draft values or validation state.
- [x] Put a labeled dirty-only Save icon immediately left of search in a reserved slot. Preserve Cancel and the existing departure guards. Submit the whole draft once, including hidden edits. Reveal and focus a hidden invalid control. While saving, keep the draft and disable duplicate writes. Clear only after success, retain after failure, and restore focus when Save disappears.
- [x] Extend `src/views/TuningAdminView.test.ts` for stable Save visibility, a save covering a filtered-out edit, rejected input and retained drafts, cancel, resets, and guarded departure. Inspect Tuning's clean and dirty header geometry at desktop and narrow widths.

Run from `apps/legion_admin`:

```powershell
pnpm exec vitest run src/views/TuningAdminView.test.ts
```
