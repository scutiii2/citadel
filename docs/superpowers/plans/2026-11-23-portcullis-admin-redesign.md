# Portcullis Admin redesign implementation plan

**Goal** — Ship the Portcullis redesign with real admin data and align the agreed Legion controls.

**Approach** — Retain Vue routes, Pinia stores, API clients, and auth gates. Adapt the production Legion patterns to Portcullis's local component copies. Keep each view responsible for its data and use component tests for changed state transitions.

**Spec** — [Portcullis Admin redesign](../specs/2026-11-23-portcullis-admin-redesign-design.md).

Work inline on the current checkout. Follow Citadel's frontend and mobile skills, token rules, existing APIs and storage keys, and the workspace test budget. Commands below run from `apps/portcullis_admin` except Task 6. Each command runs once after that task's edits.

## 1. Shell, layout, and panel primitives

- [ ] Update `src/App.vue`, `src/components/AdminNav.vue`, and `src/components/AccountMenu.vue`. Add `src/components/PortcullisHeader.vue` for the route title, toggle, Help, permission-gated config notifications, and account controls. Keep the guest theme control reachable. Use existing route metadata and nav preferences. Let native select navigation work inside Profile and return focus on Escape.
- [ ] Use the existing `PageLayout` slots and hide redundant body title copy in the authenticated shell while keeping actions visible. Add Portcullis-local `src/components/admin/AdminSearch.vue` and `RecordDrawer.vue`, following the Legion components. `AdminSearch` takes a label and string model and exposes `focus()`. The drawer takes open, title, editable, editing, busy, and optional opener state, emits edit/save/discard/close, and exposes save and cancel requests to the editor. Put shared panel, row, and toolbar geometry in `src/components/admin/admin.css`.
- [ ] Update `AdminNav.test.ts` for permissions, saved order, and current route. Add focused `PortcullisHeader.test.ts` and `RecordDrawer.test.ts` coverage for theme and logout placement, notification visibility, Escape, discard, and focus fallback. Run `pnpm exec vitest run src/components/AdminNav.test.ts src/components/PortcullisHeader.test.ts src/components/admin/RecordDrawer.test.ts src/components/PageLayout.test.ts src/router/index.test.ts`.

## 2. Account roster and multi-role edits

- [ ] Update `src/views/AccountsAdminView.vue` and `src/components/admin/AccountsPanel.vue` to retain `q` and `status` in the route. Fetch the existing complete status-filtered roster with `listAccounts({ status })` and match username, email, and role name locally. Suppress stale status requests and preserve the selected account independently of the rendered rows. Put permitted invite navigation in the roster toolbar.
- [ ] Use `RecordDrawer` with `src/components/admin/AccountDrawer.vue`. Render every `AdminAccount.roles` entry, plus an empty state. Stage role choices by ID and editable profile fields; keep enable/disable, verify, and typed deletion on their existing paths. Gate staged fields and choices by their existing permissions and delegation rules. Keep protected records read-only. Use inline errors and persistent drawer actions.
- [ ] Snapshot role IDs on edit. On confirmed save, compute intentional additions and removals from that snapshot. Apply changed profile fields first, then role additions, then removals, sequentially through `adminClient`. Update confirmed account state after every response. On failure stop, display the part that failed, and retain unconfirmed changes. Before retrying an ambiguous failure refresh the account using the existing list endpoint, then skip fulfilled operations. Discard drops pending edits without undoing confirmed writes. Refresh the current account after any confirmed self change, including partial saves, and honor any resulting access redirect.
- [ ] Update `AccountsPanel.test.ts` and `AccountDrawer.test.ts` for role-name search, two roles, empty roles, protected records, discard without writes, and retry after one of two role calls succeeds. Assert unstaged assignments survive, confirmed operations are skipped on retry, and self changes refresh access. Run `pnpm exec vitest run src/components/admin/AccountsPanel.test.ts src/components/admin/AccountDrawer.test.ts`.

## 3. Role roster and editor drawer

- [ ] Update `src/views/RolesAdminView.vue`, `src/components/admin/RolesPanel.vue`, and `src/components/admin/RoleEditor.vue`. Add searchable role rows, use the drawer for role details and editing, and move role creation and affected accounts to the right drawer. Preserve the view's existing route-leave handshake with the panel, beforeunload behavior, and role/account controls based on existing permissions.
- [ ] Connect the existing `RoleChanges` draft to validated Save and Discard confirmations. Preserve grouped permission search and its hidden edits. Keep protected fields and permissions locked, retain deletion warning and account count, and refresh auth when the actor holds a changed role. Update existing tests for hidden permission edits, failed save retaining the draft, and a guarded route change. Run `pnpm exec vitest run src/components/admin/RolesPanel.test.ts src/components/admin/RoleEditor.test.ts src/views/AdminView.test.ts`.

## 4. Invites, overview, and config issues

- [ ] Update `src/views/InvitesAdminView.vue` and `src/components/admin/InvitesPanel.vue`. Use searchable rows, an invite details drawer, and the existing email and manual flow in a create drawer. Keep `?create=1`, expiration, copy-link, revoke confirmation, and the server-assigned default role.
- [ ] Update `src/views/OverviewView.vue` with the reference navigation layout and live summary links. Update `src/views/ConfigIssuesView.vue` with `PageLayout`, local search alongside severity filters, and read-only check details. Keep file grouping, permitted access, redaction, diagnostic refresh, and the existing return home after a successful empty check.
- [ ] Extend `InvitesPanel.test.ts` for search and the existing delivery states. Add focused `src/views/ConfigIssuesView.test.ts` coverage for a failed check versus a successful empty check and search combined with severity. Run `pnpm exec vitest run src/components/admin/InvitesPanel.test.ts src/views/ConfigIssuesView.test.ts src/pageLayout.test.ts`.

## 5. Workspace settings panels

- [ ] Update `src/views/WorkspaceSettingsView.vue`, `src/components/admin/SettingsPanel.vue`, `src/components/admin/SidebarPagesPanel.vue`, and `src/components/AppConfigCard.vue`. Use a searchable header and reserved icon slots for each independent draft, keeping existing API calls and reset semantics. Confirm discard and return focus to search after the actions close. Keep all validated fields mounted under search and reveal the first hidden invalid field before a save. Keep request errors and saved/restart notices next to the owning panel.
- [ ] Extend the existing tests for hidden edits in a submitted payload, hidden invalid input blocking submission, failed save retaining edits, and discard restoring saved values. Run `pnpm exec vitest run src/components/admin/SettingsPanel.test.ts src/components/admin/SidebarPagesPanel.test.ts src/components/AppConfigCard.test.ts`.

## 6. Legion controls

- [ ] In `src/components/LegionHeader.vue`, style the native Theme select to match Portcullis with a visible label, chevron, and one inset focus outline. In `src/components/admin/AdminSearch.vue`, move focus paint to the wrapper and suppress the inner input outline. In `src/views/TuningAdminView.vue`, replace the text Cancel with a named × icon before Save. Keep two reserved slots, pending state, confirmation, search focus handoff, and whole-draft validation.
- [ ] Extend `LegionHeader.test.ts` and `TuningAdminView.test.ts` for selection, icon labels, dirty transitions, and dismissal preserving the draft. Run from `apps/legion_admin` with `pnpm exec vitest run src/components/LegionHeader.test.ts src/views/TuningAdminView.test.ts`.

While checking each changed UI, inspect the affected flow on desktop and mobile using the viewport and theme criteria in the spec. Check the rendered focus outline and spacing where they change, since DOM tests do not exercise CSS layout.
