# Armory Admin and Stronghold Admin redesign implementation plan

**Goal** — Bring Armory Admin and Stronghold Admin to the redesigned Portcullis, Legion and Treasury design, including every change made to those apps after the first Portcullis spec.

**Approach** — Copy the shared components from `apps/treasury_admin` (the newest copies; Portcullis where Treasury has none) instead of rewriting them. Keep each app's routes, Pinia auth store, API clients and permission guard. Each view keeps its own data and logic; only the markup, the panel components and the styles change. Do Armory first, then copy its proven shell into Stronghold.

**Spec** — [Armory Admin and Stronghold Admin redesign](../specs/2026-11-23-armory-stronghold-admin-redesign-design.md).

Work inline on the current checkout. Follow Citadel's frontend and mobile skills, token rules and the workspace testing budget. Commands run from the app named in each part. Each command runs once after that task's edits. Copy files exactly, then change only app names (`treasury-header` to `armory-header` or `stronghold-header`, "Treasury Admin" to the app name, `ADMIN_APPS` exclusion, port). Keep each app's existing storage keys.

## Part A. Armory Admin (`apps/armory_admin`)

### A1. Shared primitives and styles

- [ ] Copy from `apps/treasury_admin/src` into the same paths, unchanged: `components/ThemeSelect.vue`, `components/admin/{AdminSearch,RecordDrawer,StatusFilters,DraftActions,PanelHelp,StatTile}.vue`, `components/admin/RecordDrawer.test.ts`, `components/admin/PanelHelp.test.ts`, `composables/useDraftPanel.ts`. Replace `components/admin/admin.css` with Treasury's.
- [ ] Merge Treasury's admin block of `src/style.css` into Armory's (header rules renamed `.armory-header`, `.admin-panel-card`, `.admin-panel-head`, `.admin-panel-tools`, `.admin-records` with the no-wrap thead rule, `.admin-icon` with `.accent`, rounded-rectangle `.primary` with `text-decoration: none`). Keep Armory's tokens.
- [ ] Make `components/ToggleSwitch.vue` match the Treasury copy.
- [ ] Run `pnpm exec vitest run src/components/admin/RecordDrawer.test.ts src/components/admin/PanelHelp.test.ts src/radiusScale.test.ts`.

### A2. Shell, header, navigation, Overview and routing

- [ ] `src/router/pages.ts`: add Overview first (`to: "/overview"`, permission `["capabilities.manage", "tickets.manage"]`), give Limits its own icon (gauge: `["m12 14 4-4", "M3.34 19a10 10 0 1 1 17.32 0"]`), export `pageTitle(path)`. `src/router/index.ts`: add the route, redirect `/` to `/overview`. `guard.ts`: home is the first permitted page. Update `pages.test.ts`, `guard.test.ts`, `index.test.ts`.
- [ ] Replace `ArmoryNav.vue` with the Treasury sidebar (page links filtered by permission, labels expanded, named icons collapsed, `ADMIN_APPS` shortcuts without Armory, `aria-label="Armory Admin"`, `aria-current="page"`). Add `ArmoryHeader.vue` from `TreasuryHeader.vue` (toggle, identity, divider, `h1` title, Notifications, Help, Profile with `ThemeSelect` and Log out, no Ember link, Escape focus return). Help text: one line per page.
- [ ] Add `stores/notices.ts` holding the last "Armory answered" result (refreshed by Overview, Capabilities and when Notifications opens). Update `App.vue`: header plus sidebar, guest `ThemeSelect`, the `.armory-shell` rule that hides body page-head copy, the session-expiry redirect.
- [ ] Add `views/OverviewView.vue`: tiles for Capabilities (online of total), Ticket settings (tags), Settings (changed), Limits (changed), Email (configured), loaded with `Promise.allSettled` from the existing clients, shown only for permitted pages; unreachable banner with Review; shortcuts panel with `PanelHelp`; Unavailable on a failed count.
- [ ] Add `ArmoryNav.test.ts`, `ArmoryHeader.test.ts`, `OverviewView.test.ts` (counts, banner, Unavailable). Run `pnpm exec vitest run src/components/ArmoryNav.test.ts src/components/ArmoryHeader.test.ts src/views/OverviewView.test.ts src/router/guard.test.ts src/router/index.test.ts src/router/pages.test.ts src/components/PageLayout.test.ts`.

### A3. Capabilities

- [ ] Rewrite `views/CapabilitiesAdminView.vue` as one roster panel: header with `PanelHelp` (the old description), icon-only Refresh (disabled while refreshing), `StatusFilters` (All, Online, Offline with counts) and `AdminSearch` over capability and tool names. Whole row opens the details drawer through one native opener. Keep the online/offline `ToggleSwitch` (pending until the server answers), Restart, and the offline, restarting and error states.
- [ ] Details drawer on `RecordDrawer` replaces `IntegrationToolsModal` here: tool list, status, identity, the controls above. Delete `IntegrationToolsModal.vue` and its test if nothing else uses them (grep first).
- [ ] In `components/ToolRunForm.vue` replace the `checkbox` widget markup with `ToggleSwitch`; keep `aria-invalid` and `aria-describedby`.
- [ ] Update `CapabilitiesAdminView.test.ts` and `ToolRunForm.test.ts` (row opener opens the drawer, search filters rows, toggle replaces the checkbox, failed toggle shows its error). Run `pnpm exec vitest run src/views/CapabilitiesAdminView.test.ts src/components/ToolRunForm.test.ts`.

### A4. Settings pages (Ticket settings, Settings, Limits, Email)

- [ ] For each of `TicketSettingsView.vue`, `EnvironmentSettingsView.vue`, `LimitsView.vue`, `EmailSettingsView.vue`: wrap each existing `card` section in an `admin-panel-card` panel whose header holds `PanelHelp` (description and field hints moved in), `DraftActions` and `AdminSearch` over field labels. Drive dirty state, discard confirmation, focus return and route guard with `useDraftPanel`. Keep every field, validation message, "changed" tag, secret handling, saved notice and API call. Replace the text Save with `DraftActions`.
- [ ] Convert `EnvironmentSettingsView` boolean value checkbox and `EmailSettingsView` "Remove the saved password" checkbox to `ToggleSwitch`. Ticket settings' tag add/remove become icon buttons with aria-labels.
- [ ] Update the four `*View.test.ts` files to the new markup. Add one case on Email or Settings that search keeps a pending draft and one that a failed save keeps input. Run `pnpm exec vitest run src/views/TicketSettingsView.test.ts src/views/EnvironmentSettingsView.test.ts src/views/LimitsView.test.ts src/views/EmailSettingsView.test.ts`.

### A5. Login, docs and e2e

- [ ] `LoginView.vue` and `NoAccessView.vue`: guest `ThemeSelect` and shared button radius only. Remove old rail styles and unused imports/classes (`SettingRow.vue`, `DeleteButton.vue`, `infoPage.css` and `pageLayout.css` rules, `.page-search`) once grep shows no use.
- [ ] Update `AGENTS.md`: shared component list, drawers not modals, no checkboxes, `PanelHelp` on every panel header, Overview page, icon actions in headers, Playwright command.
- [ ] `pnpm add -D @playwright/test`, add `playwright.config.ts` (port 5198, `ARMORY_E2E_PORT`) and `test:e2e` script copied from Treasury. Add `e2e/fakeApi.ts` answering every `/api` call the app makes and recording unexpected ones, plus `shell.spec.ts`, `pages.spec.ts` (all six pages, both themes, 1280/768/375, no horizontal scroll, no unexpected request) and `drawer.spec.ts` (Capabilities drawer: expand, restore, own-body scroll, footer reachable, discard).
- [ ] Run `pnpm exec vue-tsc -b`, `pnpm exec vitest run src/radiusScale.test.ts`, then `pnpm run test:e2e`.
- [ ] Check all pages in the browser at desktop, 768px, 767px and 375px in Light and Dark: last-row hover and focus, search outline, help popover, drawer expand and restore, no-wrap status filters.

## Part B. Stronghold Admin (`apps/stronghold_admin`)

### B1. Shared primitives and styles

- [ ] Repeat A1 here with the same file list, unchanged copies from Treasury, `.stronghold-header` rename, and the `ToggleSwitch` match. Keep `SegmentedControl.vue` as is.
- [ ] Run `pnpm exec vitest run src/components/admin/RecordDrawer.test.ts src/components/admin/PanelHelp.test.ts src/radiusScale.test.ts`.

### B2. Shell, header, navigation, Overview and routing

- [ ] `src/router/pages.ts`: fix Analytics to `permission: ANALYTICS_PERMISSIONS` (the constant, not a string); add Overview first with permission `["usage.all.view", ...ANALYTICS_PERMISSIONS, "tickets.manage", "settings.manage", "tool_services.manage"]`; export `pageTitle(path)`. Add the `/overview` route and `/` redirect in `index.ts`, home-page logic in `guard.ts`. Add `src/router/pages.test.ts` with a case that Analytics is allowed for an account holding only `traffic.view`, and update `guard.test.ts`, `index.test.ts`.
- [ ] Replace `StrongholdNav.vue` and add `StrongholdHeader.vue` exactly as in A2 (names, `ADMIN_APPS` without Stronghold, `aria-label="Stronghold Admin"`). `stores/notices.ts` holds the last "Stronghold answered" result, refreshed by Overview, Usage, Tool services and when Notifications opens. Update `App.vue` with the `.stronghold-shell` rule.
- [ ] Add `views/OverviewView.vue`: tiles for Usage, Analytics, Tickets (open), Tool services (enabled of total), Usage settings, Brain settings, each shown only when permitted, `Promise.allSettled` over the existing clients, banner, shortcuts panel with `PanelHelp`, Unavailable on failure.
- [ ] Add `StrongholdNav.test.ts`, `StrongholdHeader.test.ts`, `OverviewView.test.ts`. Run `pnpm exec vitest run src/components/StrongholdNav.test.ts src/components/StrongholdHeader.test.ts src/views/OverviewView.test.ts src/router/pages.test.ts src/router/guard.test.ts src/router/index.test.ts src/components/PageLayout.test.ts`.

### B3. Usage and Analytics

- [ ] `UsageView.vue`: one roster panel with `PanelHelp`, `AdminSearch` over user name and the export action as an icon button. Whole row opens a `RecordDrawer` with the account's usage and limits; the Entries link keeps its target. Update `UsageView` tests.
- [ ] `AnalyticsView.vue`: keep the tabs as a `SegmentedControl` in the panel header; each tab is a panel with `PanelHelp` and an icon Refresh; Entries gets `AdminSearch`; opening a log entry or chat turn uses `RecordDrawer` (reuse `ChatTurnEntry`). Update `AnalyticsView.test.ts`.
- [ ] Run `pnpm exec vitest run src/views/AnalyticsView.test.ts src/views/UsageView.test.ts`.

### B4. Tickets

- [ ] Replace the `<aside>` in `components/admin/TicketDrawer.vue` with `RecordDrawer` (Edit, Expand, Close; footer Save and Cancel; discard confirmation). Give the `TicketsPanel.vue` header `PanelHelp`, `AdminSearch`, `StatusFilters` over the existing statuses and icon actions. Keep ticket data, triage and permissions. Update `TicketDrawer.test.ts` and `TicketsPanel.test.ts`.
- [ ] Run `pnpm exec vitest run src/components/admin/TicketDrawer.test.ts src/components/admin/TicketsPanel.test.ts`.

### B5. Settings pages and Tool services

- [ ] `UsageSettingsView.vue` and `BrainSettingsView.vue`: apply the A4 pattern (panels, `PanelHelp` carrying the descriptions and the "where the files are kept" note, `DraftActions`, `AdminSearch`, `useDraftPanel`). Prices rows add and remove become icon buttons. Update both view tests; run `pnpm exec vitest run src/views/UsageSettingsView.test.ts src/views/BrainSettingsView.test.ts`.
- [ ] `ToolServicesView.vue`: one roster panel with `PanelHelp`, `StatusFilters` (All, Enabled, Disabled), `AdminSearch` over name and address. The row opens a `RecordDrawer` holding the Enabled `ToggleSwitch` (pending until the server answers), address rows (Remove address as icon button, Add address), discovered origins and the existing confirmations. Failed saves keep the draft. Update `ToolServicesView.test.ts`; run `pnpm exec vitest run src/views/ToolServicesView.test.ts`.

### B6. Login, docs and e2e

- [ ] `LoginView.vue`, `NoAccessView.vue`, cleanup of unused rail styles and imports as in A5.
- [ ] Update `AGENTS.md` as in A5. Add Armory and Stronghold to the shared-component copy list in the frontend skill.
- [ ] `pnpm add -D @playwright/test`, `playwright.config.ts` (port 5197, `STRONGHOLD_E2E_PORT`), `test:e2e` script, `e2e/fakeApi.ts`, `shell.spec.ts`, `pages.spec.ts` (all seven pages including Overview), `drawer.spec.ts` (Tool services drawer).
- [ ] Run `pnpm exec vue-tsc -b`, `pnpm exec vitest run src/radiusScale.test.ts`, then `pnpm run test:e2e`.
- [ ] Browser check as in A5 for all pages, plus the Analytics tabs.
