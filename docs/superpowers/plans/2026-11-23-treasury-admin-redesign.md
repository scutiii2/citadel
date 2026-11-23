# Treasury Admin redesign implementation plan

**Goal** — Bring Treasury Admin to the redesigned Portcullis and Legion design, including every change made to those two apps after the first Portcullis spec.

**Approach** — Copy the shared components from `apps/portcullis_admin` (the newest copies) instead of rewriting them. Keep the routes, Pinia auth store, API client and permission guard. Each view keeps its own data and logic; only the markup, the panel components and the styles change.

**Spec** — [Treasury Admin redesign](../specs/2026-11-23-treasury-admin-redesign-design.md).

Work inline on the current checkout. Follow Citadel's frontend and mobile skills, token rules and the workspace testing budget. Commands run from `apps/treasury_admin`. Each command runs once after that task's edits. Copy files exactly, then change only app names (Portcullis to Treasury, `portcullis-header` to `treasury-header`). Treasury keeps its existing storage keys.

## 1. Shared primitives and styles

- [ ] Copy these files from `apps/portcullis_admin/src` into the same paths here, unchanged: `components/ThemeSelect.vue`, `components/admin/AdminSearch.vue`, `components/admin/RecordDrawer.vue`, `components/admin/RecordDrawer.test.ts`, `components/admin/StatusFilters.vue`, `components/admin/DraftActions.vue`, `components/admin/PanelHelp.vue`, `components/admin/PanelHelp.test.ts`, `components/admin/StatTile.vue`, `composables/useDraftPanel.ts`. Add `components/admin/admin.css` from Portcullis.
- [ ] Merge the Portcullis admin block of `src/style.css` into Treasury's `style.css` (the tokens already match): the `.portcullis-header` rules renamed `.treasury-header`, `.admin-panel-card`, `.admin-panel-head`, `.admin-panel-tools`, `.admin-records` with the no-wrap thead rule, `.admin-icon` with `.accent`, and the rounded-rectangle `.primary` rules with `text-decoration: none`. Keep Treasury's existing tokens.
- [ ] Make `ToggleSwitch.vue` match the Portcullis copy if they differ. `StatusFilters.vue` keeps `flex-wrap: nowrap; overflow-x: auto` with buttons `flex: 1 0 auto; white-space: nowrap`.
- [ ] Run `pnpm exec vitest run src/components/admin/RecordDrawer.test.ts src/components/admin/PanelHelp.test.ts src/radiusScale.test.ts`.

## 2. Shell, header and navigation

- [ ] Replace the icon rail in `src/components/TreasuryNav.vue` with the sidebar from Portcullis `AdminNav.vue`: page links filtered by permission, an Overview link first, labels expanded and named icons collapsed, and the other admin apps at the bottom from `ADMIN_APPS` excluding Treasury (port 26505). Keep `aria-label="Treasury Admin"` on the landmark and `aria-current="page"`.
- [ ] Add `src/components/TreasuryHeader.vue` from `PortcullisHeader.vue`: toggle, "Treasury Admin" identity, divider, page title (`h1`), then Notifications, Help and Profile. Notifications show one row (icon, title, note, chevron) while Treasury does not answer, with a count badge and the "You're all caught up" empty state. Help explains the pages and the "applies now / from the next start" wording. Profile shows the identity, `ThemeSelect` and Log out only: Treasury has no Profile or Settings page, and there is no Ember link. Escape returns focus to the trigger.
- [ ] Add `src/stores/notices.ts` holding the last Treasury reachability result, so the header, Overview and Instances share one source. It refreshes when the Notifications popover opens and when Instances loads.
- [ ] Update `src/App.vue`: header plus sidebar shell, a guest `ThemeSelect` on login, `pageTitle(route.path)` exported from `router/pages.ts`, the narrow-screen toggle that discloses the sidebar above the content, and the existing redirect to login on session expiry. Hide redundant page-head copy in the signed-in shell with a `.treasury-shell` rule, as Portcullis does.
- [ ] Add `TreasuryNav.test.ts` (permissions, order, current page, shortcuts without Treasury) and `TreasuryHeader.test.ts` (Profile content with no Ember link, notification rows and empty state, Escape focus return). Run `pnpm exec vitest run src/components/TreasuryNav.test.ts src/components/TreasuryHeader.test.ts src/components/PageLayout.test.ts src/router/index.test.ts`.

## 3. Overview page and routing

- [ ] Add `/overview` to `src/router/pages.ts` as the first page with permission `settings.manage`, plus the `pageTitle` helper. Add its route in `src/router/index.ts`, redirect `/` to `/overview`, and make `guard.ts` use the first permitted page as home. Update `guard.test.ts` and `index.test.ts`.
- [ ] Add `src/views/OverviewView.vue` on the Legion and Portcullis pattern: four stat tiles with an icon, a count and a footer link (Instances, Connections, Services, Outside services), loaded with `Promise.allSettled` from `treasuryAdminClient.get`, `connections`, `getServices` and `getOutside`. Add a warning banner with a Review button when Treasury does not answer, and a "Treasury Admin" panel with `PanelHelp` listing the pages with live details. A count that failed shows Unavailable, never zero.
- [ ] Add `OverviewView.test.ts` for the counts, the unreachable banner, and Unavailable on a failed request. Run `pnpm exec vitest run src/views/OverviewView.test.ts src/router/guard.test.ts src/router/index.test.ts`.

## 4. Connections

- [ ] Rewrite `src/views/ConnectionsView.vue` as two panels. **Connections roster:** a header with `PanelHelp` (the old description, the "applies now / next start" note and the Postgres `${NAME}` placeholder note), an icon-only Add connection button (filled accent plus), and `AdminSearch` over name, type, where and instance names. `StatusFilters` above it for All, Built-in, Saved and Changed with counts. The whole row opens its details drawer through one native opener; Edit, Expand and Close sit in the drawer header. **Cache defaults panel:** `PanelHelp`, `DraftActions` and `AdminSearch`, the three number fields, "Use the built-in defaults" kept as a chip, discard confirmation and focus return through `useDraftPanel`.
- [ ] Use `RecordDrawer` for add and edit. Keep every field per type (SQLite file; Postgres address and pool size; Firestore project, credentials file and database), the per-connection cache, `formError` and the saved notice. Replace the raw-SQL checkbox with a `ToggleSwitch`. Put Remove and "Use the built-in" last in the drawer, still through `ConfirmModal`. Validate before the save confirmation, confirm discard on Cancel, Close, Escape and backdrop, and keep the draft after a failed save.
- [ ] Update `ConnectionsView.test.ts` for the drawer flow, search keeping a draft, the toggle, and a failed save keeping input. Run `pnpm exec vitest run src/views/ConnectionsView.test.ts`.

## 5. Instances, Services and Outside services

- [ ] **Instances** (`InstancesView.vue`): one roster panel with `PanelHelp` carrying the old description, an icon-only Refresh (refresh icon, disabled while loading) and `AdminSearch` over instance and connection names. A row opens a details drawer with the connections and the Portcullis data note. "Treasury does not answer" stays a distinct error and updates the shared notice state.
- [ ] **Services** (`ServicesView.vue`): one roster panel with `PanelHelp` carrying the old description, `StatusFilters` for All, Pinned, Registered and Default, and `AdminSearch` over name and address. Move the per-row pin form into the details drawer: Edit stages the address, and Pin and "Use the registered address" sit in the footer after confirmation. Never show an unconfirmed address. Keep the table in a labeled local scroller.
- [ ] **Outside services** (`OutsideView.vue`): one roster panel of groups with `PanelHelp` and `AdminSearch` over group name, origin and service id. Rename and origin removal move into the group drawer. Keep the `applyView` draft keeping, the "Name saved. Could not refresh" message and the existing confirmations. A failed rename keeps its draft inside the drawer.
- [ ] Update `InstancesView.test.ts`, `ServicesView.test.ts` and `OutsideView.test.ts` to the new markup, and add a test that search keeps a pending draft on Services. Run `pnpm exec vitest run src/views/InstancesView.test.ts src/views/ServicesView.test.ts src/views/OutsideView.test.ts`.

## 6. Login, docs, skill and e2e

- [ ] Update `LoginView.vue` and `NoAccessView.vue` only for the guest `ThemeSelect` and the shared button radius. Remove the old rail styles and unused classes from `TreasuryNav.vue`, `infoPage.css` and `pageLayout.css`, and any imports that are now unused, such as `SettingRow.vue` and `DeleteButton.vue`.
- [ ] Update `apps/treasury_admin/AGENTS.md`: the shared component list, drawers not modals, no checkboxes, every panel header has `PanelHelp`, the Overview page, and icon actions in panel headers. Add Treasury to the shared-component copy list in the frontend skill.
- [ ] Add `@playwright/test` with `pnpm add -D @playwright/test`, a `playwright.config.ts` and a `test:e2e` script copied from Portcullis (spare port 5199), and `e2e/fakeApi.ts` that answers every `/api` call and records unexpected ones. Add three specs: the shell (sidebar at 1280, 768 and 375, Profile theme persisted, Escape focus), the five pages at desktop, tablet and mobile in both themes with no horizontal page scroll and no unexpected request, and the drawer (expand, restore, own-body scroll, footer reachable, discard, full-width expand on phones).
- [ ] Run `pnpm exec vue-tsc -b`, then `pnpm exec vitest run src/radiusScale.test.ts src/pageLayout.test.ts`, then `pnpm run test:e2e`.
- [ ] Check the five pages in the browser at desktop, 768px, 767px and 375px in Light and Dark: last-row hover and focus corners, search focus outline, the help popover, drawer expand and restore, and the no-wrap status filters.
