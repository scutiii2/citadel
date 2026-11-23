# Ember redesign Implementation Plan

> **For agentic workers:** run the tasks in order in the current checkout. No baseline run, no branch, no commit per task, no review step between tasks. Report once at the end. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Bring `apps/ember` to the panel, drawer and control patterns of the redesigned admin apps without changing its rail, tab bar or chat.

**Architecture:** Copy the shared admin primitives into a new `src/components/ui/panel/` folder, then convert each page: `PanelHelp` in panel headers, `RecordDrawer` instead of page-opened `BaseModal`s, `SettingsPanel` for Settings and Profile, `StatTile`s on Overview.

**Tech Stack:** Vue 3, TypeScript, Pinia, vitest + @vue/test-utils, Playwright, pnpm.

**Spec:** [2026-11-23-ember-redesign-design.md](../specs/2026-11-23-ember-redesign-design.md)

## Global Constraints

- Work in `apps/ember`. `ember_web` is not touched. Chat and its dialogs (`features/chat/**`) stay as they are.
- Copies come from `apps/treasury_admin/src` (`components/admin/*`, `composables/useDraftPanel.ts`) and `apps/armory_admin/src/components/admin/SettingsPanel.vue`. Do not edit the originals.
- Radius only through `--radius-*`, colors only through `style.css` tokens. Never add reduced-motion code. pnpm only.
- Panel header: `PanelHelp` first among tools; actions are `admin-icon` buttons (`accent` for primary) with `aria-label` and `title`.
- Only `ConfirmModal` stays modal outside chat. A `RecordDrawer` wraps `BaseModal` in `side` mode.
- Checks per task: the listed test files once, then `pnpm exec vue-tsc -b` in `apps/ember`. Run from `apps/ember`.

---

### Task 1: Copy the shared primitives

**Files:**
- Create: `src/components/ui/panel/{PanelHelp,RecordDrawer,DraftActions,StatTile,StatusFilters,SettingsPanel,AdminSearch}.vue`, `PanelHelp.test.ts`, `RecordDrawer.test.ts`, `admin.css`
- Create: `src/composables/useDraftPanel.ts`
- Modify: `src/style.css` (add the admin block), `src/components/ui/dialogs/BaseModal.vue` only if its `side` mode differs from Treasury's copy

**Interfaces:**
- Produces: the same props, slots and emits as the Treasury copies (`RecordDrawer`: `open`, `title`, `editing`, `dirty`, `@close`, `@save`; `SettingsPanel`: props `title, heading, label, dirty, saving`, `v-model:search`, slots `help`, `tools`, default, emits `discard`, `save`).

- [ ] **Step 1:** Copy the files listed above byte for byte. Fix the relative imports (`../ui/dialogs/BaseModal.vue`, `ConfirmModal.vue`, `useDraftPanel`) to Ember's paths. Keep the no-glow `.panel-help` rule (no `box-shadow`).
- [ ] **Step 2:** Diff Ember's `BaseModal.vue` and `ConfirmModal.vue` against Treasury's; port any missing `side`-mode or focus-return behavior that `RecordDrawer` relies on.
- [ ] **Step 3:** Append to `src/style.css` the admin block Treasury uses (`.admin-icon`, `.admin-icon.accent`, `.admin-panel-card`, `.admin-panel-head`, `.admin-panel-tools`, `.admin-panel-text`, rounded-rectangle `.primary`), renamed only where Treasury names its own shell. Import `components/ui/panel/admin.css` where Ember imports global CSS.
- [ ] **Step 4:** Run `pnpm exec vitest run src/components/ui/panel src/radiusScale.test.ts src/themeContrast.test.ts` and `pnpm exec vue-tsc -b`. Expected: pass.

### Task 2: Guard `BaseModal` imports

**Files:**
- Modify: `src/architecture.test.ts`

- [ ] **Step 1:** Add a test that scans `src/features/**` and `src/components/**` Vue files and fails when a file outside `features/chat/**`, `components/ui/dialogs/**` and `components/ui/panel/**` imports `BaseModal`. Start with an allow-list of the files that still import it, so the test passes now and shrinks as Tasks 3 to 8 remove entries. Each later task deletes its files from the list.
- [ ] **Step 2:** Run `pnpm exec vitest run src/architecture.test.ts`. Expected: pass.

### Task 3: Overview tiles

**Files:**
- Modify: `src/features/overview/OverviewView.vue`, `OverviewView.test.ts`

- [ ] **Step 1:** Add a `PanelHelp` to the page's main panel (content from the current intro text).
- [ ] **Step 2:** Add `StatTile`s, each shown only when `auth.hasPermission` allows the target page and linking to it: Tickets (open or unread via `ticketsClient.unreadCount`), Agents (running of total from the agents store or client the Agents page uses), Capabilities (online of total, `commandsClient.capabilities`), Usage (period tokens from the usage client). Load each in its own try/catch; a failed load shows `Unavailable`, never `0`.
- [ ] **Step 3:** Update `OverviewView.test.ts`: tile hidden without permission, count shown, `Unavailable` on a rejected client.
- [ ] **Step 4:** Run `pnpm exec vitest run src/features/overview`. Expected: pass.

### Task 4: Settings and Profile as `SettingsPanel`

**Files:**
- Modify: `src/features/settings/SettingsView.vue`, `SettingsView.test.ts`, `src/features/account/AccountView.vue`, `AccountView.test.ts`

- [ ] **Step 1:** Wrap `SettingsView` in one `SettingsPanel` (`PanelHelp` carrying the old description, search over section titles, sections hidden with `v-show`). Browser-local preferences stay outside the draft and keep "Applies instantly. Saved on this device." in `PanelHelp`. Admin-only tool approval becomes the draft section with `DraftActions`.
- [ ] **Step 2:** Do the same in `AccountView`: profile fields that save together are the draft; password change and sessions keep their own actions; destructive actions keep the Danger zone and `ConfirmModal`.
- [ ] **Step 3:** Convert any boolean option in these pages to `ToggleSwitch` (no checkboxes); a switch that calls the server stays pending until it answers.
- [ ] **Step 4:** Update both view tests: Save absent when clean, present when dirty, search keeps a draft, discard asks first and writes nothing. Run `pnpm exec vitest run src/features/settings src/features/account`. Expected: pass.

### Task 5: Capabilities and Agents

**Files:**
- Create: `src/features/capabilities/components/CapabilityDrawer.vue` (+ test), `src/features/capabilities/components/UserExtensionDrawer.vue` (+ test), `src/components/tools/forms/ToolRunDrawer.vue`, `CommandFormDrawer.vue`
- Delete: `ToolRunModal.vue`, `CommandFormModal.vue`, `UserExtensionModal.vue` and their tests
- Modify: `src/features/capabilities/views/CapabilitiesView.vue` (+ test), `src/features/agents/AgentsView.vue` (+ test)

- [ ] **Step 1:** Rebuild each deleted modal as a `RecordDrawer` with the same props and events (the views change only the component name), single-column layout, Save and Cancel in the footer where the modal had them, `ToolRunForm` unchanged.
- [ ] **Step 2:** `CapabilitiesView`: `PanelHelp`, `StatusFilters` (All, Online, Offline) over the existing capability state, `SearchField`, icon Refresh; the row opener name is `Open <capability>`.
- [ ] **Step 3:** `AgentsView`: `PanelHelp` and `SearchField` in the header; the description modal becomes a `RecordDrawer`. Remove these files from the Task 2 allow-list.
- [ ] **Step 4:** Update the view and component tests to drawer markup (add a `HTMLDialogElement.showModal` polyfill in the test file if jsdom lacks it). Run `pnpm exec vitest run src/features/capabilities src/features/agents src/components/tools`. Expected: pass.

### Task 6: Tickets and Usage

**Files:**
- Modify: `src/features/tickets/TicketsView.vue` (+ test), `src/features/usage/UsageView.vue` (+ test)

- [ ] **Step 1:** `TicketsView`: `PanelHelp`, status filter as `StatusFilters`, `SearchField`, icon New ticket (`accent`). The new-ticket form and the ticket thread open in `RecordDrawer` (replaces `BaseModal class="new-ticket-modal"`). Keep the `tickets-seen` event and unread badge.
- [ ] **Step 2:** `UsageView`: `PanelHelp`, the period `SegmentedControl` and an icon Refresh in the header. No drawer unless a row already opens a modal.
- [ ] **Step 3:** Update tests, remove `TicketsView.vue` from the Task 2 allow-list. Run `pnpm exec vitest run src/features/tickets src/features/usage`. Expected: pass.

### Task 7: Notes, Skills, Shares and Global

**Files:**
- Modify: `src/features/notes/NotesView.vue`, `skills/SkillsView.vue`, `sharing/SharesView.vue`, `global/GlobalView.vue` (+ tests)
- Modify: `src/features/sharing/components/ShareDialog.vue`, `ShareReview.vue`, `src/features/global/components/GlobalFileDialog.vue`, `GlobalReview.vue`, `GlobalSkills.vue`, `src/features/proposals/components/ProposalsDialog.vue` (+ tests)

- [ ] **Step 1:** Add `PanelHelp` to each list or reader header and move its description text into it. Keep `ListEditorLayout`, `ListRow`, `SearchField` and mobile Back.
- [ ] **Step 2:** In the six dialog files, replace `BaseModal` with `RecordDrawer` (same props and events, wide dialogs use the drawer's Expand). Rename files to `*Drawer.vue` only when the name says "Dialog"; update imports and tests.
- [ ] **Step 3:** In `ProposalsDialog.vue` the "remove items" checkbox is an on/off option: make it a `ToggleSwitch`. In `TriageQuestionModal.vue` (chat, exempt) leave the checkbox.
- [ ] **Step 4:** Remove these files from the Task 2 allow-list. Run `pnpm exec vitest run src/features/notes src/features/skills src/features/sharing src/features/global src/features/proposals`. Expected: pass.

### Task 8: Generator, PDF merger, Media downloader

**Files:**
- Modify: `src/features/generator/GeneratorView.vue`, `pdfMerger/PdfMergerView.vue`, `mediaDownloader/MediaDownloaderView.vue` (+ tests)

- [ ] **Step 1:** `PanelHelp` in each tool panel header; text buttons in headers become `admin-icon` buttons with names.
- [ ] **Step 2:** `PdfMergerView` "Output options" and `MediaDownloaderView` "File details" become `RecordDrawer`s. Job and download behavior unchanged.
- [ ] **Step 3:** Remove them from the Task 2 allow-list (it must now hold only chat, `ui/dialogs` and `ui/panel` paths, so replace it with the path rule). Run `pnpm exec vitest run src/features/generator src/features/pdfMerger src/features/mediaDownloader src/architecture.test.ts`. Expected: pass.

### Task 9: e2e specs and docs

**Files:**
- Create: `playwright.config.ts`, `e2e/fakeApi.ts`, `e2e/pages.spec.ts`, `e2e/drawer.spec.ts`
- Modify: `package.json` (`@playwright/test ^1.65.1`, `"test:e2e": "playwright test"`), `AGENTS.md`, `.agents/skills/ember-frontend-design/SKILL.md`

- [ ] **Step 1:** Copy `playwright.config.ts` and `e2e/*` from `apps/stronghold_admin`. Pick the port: choose the lowest free number in `26500–26999` that no other `playwright.config.ts` or `vite.config.ts` uses (grep `apps/*/playwright.config.ts` and `vite.config.ts`), set it in config with `EMBER_E2E_PORT` as override. Run `pnpm install` to update the lockfile.
- [ ] **Step 2:** `fakeApi.ts` answers the calls the pages make (`/api/auth/me` with `chat.use`, `tools.execute`, `tickets.create` permissions, tickets, usage, capabilities, agents, settings). Unlisted calls go into `state.unexpected`.
- [ ] **Step 3:** `pages.spec.ts`: Overview, Capabilities, Agents, Usage, Notes, Skills, Shares, Tickets, Settings at 1280, 768 and 375 in dark and light; each shows a `PanelHelp` button (`/^About /`) and no horizontal page scroll, and `state.unexpected` is empty. `drawer.spec.ts`: open a Capabilities drawer, expand and restore at three widths, body scrolls on its own, footer stays in view, Cancel on a dirty draft asks, focus returns to the opener.
- [ ] **Step 4:** Update `AGENTS.md` (rules: drawers, `PanelHelp`, icon actions, no checkboxes, `SettingsPanel`, the copy list, `pnpm run test:e2e` and the port) and the frontend skill's shared-component list (Ember has the panel copies).
- [ ] **Step 5:** Run `pnpm exec vue-tsc -b` then `pnpm run test:e2e`. Expected: pass.

### Final report

Report once: files changed, tests run per task, and not done (browser visual check at 768 and 767 px, Windows Tauri shell).
