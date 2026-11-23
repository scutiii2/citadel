# Armory Admin and Stronghold Admin redesign specification

Bring Armory Admin and Stronghold Admin to the design of the redesigned [Portcullis Admin](2026-11-23-portcullis-admin-redesign-design.md), Legion Admin and [Treasury Admin](2026-11-23-treasury-admin-redesign-design.md). Follow the [Citadel frontend skill](../../../.agents/skills/ember-frontend-design/SKILL.md) and its [mobile guide](../../../.agents/skills/ember-frontend-design/mobile-ui.md). Shared components stay identical copies across all five admin apps. Treasury Admin holds the newest copies, so copy from `apps/treasury_admin` (or Portcullis where Treasury has none).

## Today

Both apps use the old shell and patterns: a 52px icon rail (`ArmoryNav.vue`, `StrongholdNav.vue`) with a cycling theme button and Log out, no header, a page title and description in every body, inline `card` forms with a text Save, no search, no drawers, no `PanelHelp`. Neither has e2e specs, `ThemeSelect`, `AdminSearch`, `RecordDrawer`, `StatusFilters`, `DraftActions`, `StatTile` or `useDraftPanel`.

**Armory Admin** (port 26503) has five pages, each gated by `capabilities.manage` except Ticket settings (`tickets.manage`): Capabilities (a card list, a search box, a Refresh button, an `IntegrationToolsModal` for the tools of one capability), Ticket settings, Settings (environment values), Limits, Email.

**Stronghold Admin** (port 26504) has six pages: Usage (`usage.all.view`), Analytics (any of `ANALYTICS_PERMISSIONS`; Overview, Traffic and Entries tabs), Tickets (`tickets.manage`; `TicketsPanel`, `TicketBoard` and a hand-written `TicketDrawer` `<aside>`), Usage settings and Brain settings (`settings.manage`), Tool services (`tool_services.manage`; one editable card per service).

Known defects fixed on the way:
- `stronghold_admin/src/router/pages.ts` sets Analytics `permission: "ANALYTICS_PERMISSIONS"` (a string literal, not the constant). The nav then hides Analytics from every account that does not hold a permission with that exact name. Use the constant.
- Armory's Settings and Limits entries share one icon. Give Limits its own.
- Armory has two checkbox controls in forms that are not acknowledgements (see below).

## Shell and navigation (both apps)

- Replace the rail with the compact full-width header and sidebar from Treasury Admin (`TreasuryHeader.vue`, `TreasuryNav.vue`), renamed `ArmoryHeader`/`ArmoryNav` and `StrongholdHeader`/`StrongholdNav`. Header left: sidebar toggle, app identity, divider, current page title (`h1`, `pageTitle(route.path)` exported from `router/pages.ts`). Header right: Notifications, Help, Profile. Profile holds identity, the labeled Dark/Light/System `ThemeSelect` and Log out only (neither app has a Profile or Settings page; no Ember link). A signed-out page keeps a reachable `ThemeSelect`.
- Page entries come from `ARMORY_PAGES` and `STRONGHOLD_PAGES`, filtered by permission as now. Overview is the first entry and the landing page. The sidebar shows labels expanded and named icons collapsed; below 768px the header toggle discloses it above the content. Other admin apps sit at the bottom from `ADMIN_APPS`, excluding the current one.
- Notifications show only signals the app already has: the app's own service not answering (Armory: the capability list fails to load; Stronghold: the Overview, Usage or Tool services request fails with a network or 5xx error). A small `stores/notices.ts` (as in Treasury) holds the last result so header, Overview and the page share one source. With none, show the empty state. No config-issue counts, no invented numbers.
- Help explains each page in one line and says which pages apply now and which need a restart (Armory Settings and Limits: use the wording the pages carry today).
- The header is the only visible page title. Pages drop `description` from the body in the signed-in shell (`.armory-shell`, `.stronghold-shell` rules, as Treasury does) and keep task-specific headings and notices. Keep the redirect to login on session expiry and the no-access behavior.
- Copy without changes: `ThemeSelect.vue`, `composables/useDraftPanel.ts`, `components/admin/{AdminSearch,RecordDrawer,StatusFilters,DraftActions,PanelHelp,StatTile}.vue` with their tests, `admin.css`, and the admin block of `style.css` (header rules renamed, `.admin-panel-card`, `.admin-panel-head`, `.admin-panel-tools`, `.admin-records`, `.admin-icon` with `.accent`, rounded-rectangle `.primary` with no underline). Keep `useTheme` and its storage keys, and each app's existing tokens.

## Rules carried over from Portcullis, Legion and Treasury

- **Drawers, not modals.** Anything opened from a panel opens in `RecordDrawer`. Only `ConfirmModal` stays modal.
- **Panel headers.** Every panel header starts its tools with `PanelHelp`, then optional `StatusFilters`, `DraftActions` where the panel holds a draft, and a labeled `AdminSearch`. Header actions are icon buttons (`admin-icon`, filled `accent` for the primary one) with an accessible name and a tooltip. Static explanatory text (page descriptions, field hints that are not per-field help) moves into the `PanelHelp` popover.
- **No checkboxes** except acknowledgements and checklists. Convert to `ToggleSwitch`.
- **Primary buttons** are rounded rectangles (`--radius-md`); links styled as buttons have no underline. Secondary chips stay pills.
- **Status filters** stay on one row and scroll sideways when narrow.
- **Rows** open details through one native opener with row-wide focus, clipped inside the rounded panel, wide tables in a labeled local scroller. Focus returns to the row, or to search when the row is gone.
- **Drafts.** Settings panels use `useDraftPanel` and `DraftActions`: Cancel × and Save slots reserved and shown only while dirty, discard confirmed, focus returned to search. Search hides fields only; it never drops a draft, and pending fields are validated even when hidden.
- **Switches** that call the server stay pending until it answers. No reduced-motion code. Radius and color only through tokens.

## Armory Admin pages

- **Overview** (`/overview`, permission `["capabilities.manage", "tickets.manage"]`). Stat tiles built only from data the existing clients return, each with an icon, a count and a footer link to its page, shown only when the account may open that page: Capabilities (online of total), Ticket settings (tags), Settings (values changed from the default), Limits (changed), Email (configured or not). A banner when Armory does not answer. A panel of page shortcuts with live details and `PanelHelp`. A count that failed to load shows Unavailable, never zero.
- **Capabilities.** One roster panel (icon-only Refresh as the panel action, `PanelHelp` carrying the old description, `StatusFilters` for All, Online, Offline, `AdminSearch` over capability and tool names). The whole row opens a details drawer on `RecordDrawer` with the tool list, status and the per-capability controls that exist today (the online/offline `ToggleSwitch`, Restart). Replace `IntegrationToolsModal` use with the drawer; `ToolRunForm` stays, and its boolean `checkbox` widget becomes a `ToggleSwitch`. Keep the pending, offline, restarting and error states as they are.
- **Ticket settings, Limits, Email, Settings.** Each page becomes one or more `admin-panel-card` panels with `PanelHelp`, `DraftActions` and `AdminSearch` over its field labels, driven by `useDraftPanel`. Keep every field, validation message, "changed" tag, secret handling and saved notice. Email's "Remove the saved password" checkbox and Settings' boolean value checkbox become `ToggleSwitch`es. Ticket settings' tag list keeps its add and remove rows as icon buttons.

## Stronghold Admin pages

- **Overview** (`/overview`, permission list of every page permission). Tiles from the existing clients, each linking to its page and shown only when permitted: Usage (accounts with usage), Analytics (errors or entries in the window, only if the log permissions allow it), Tickets (open), Tool services (enabled of total), Usage settings (limits changed), Brain settings (changed). A banner when Stronghold does not answer, a shortcuts panel with `PanelHelp`, Unavailable on a failed count.
- **Usage.** One roster panel of accounts with `PanelHelp` (old description), `AdminSearch` over user name, and the existing export action as an icon button. A row opens a details drawer with the account's usage and limits; the existing Entries link keeps its target.
- **Analytics.** Keep the Overview, Traffic and Entries tabs as a `SegmentedControl` inside the panel header. Each tab is a panel with `PanelHelp` and an icon Refresh. Entries gets `AdminSearch`. Opening one chat turn or log entry uses `RecordDrawer`. Charts keep their data contracts.
- **Tickets.** Keep `TicketsPanel` and `TicketBoard` behavior. Replace the hand-written `TicketDrawer` `<aside>` with `RecordDrawer` (Edit, Expand, Close, footer Save and Cancel, discard confirmation), and give the panel header `PanelHelp`, `AdminSearch`, `StatusFilters` for the existing statuses and icon actions. Ticket data, triage and permissions are unchanged.
- **Usage settings and Brain settings.** Same pattern as the Armory settings pages: panels with `PanelHelp`, `DraftActions`, `AdminSearch`, `useDraftPanel`. Keep the Prices table add and remove rows (icon buttons), limits validation and "where the files are kept" note (moves into `PanelHelp`).
- **Tool services.** One roster panel of services with `PanelHelp`, `StatusFilters` (All, Enabled, Disabled), `AdminSearch` over service name and address. The row opens a drawer holding the Enabled `ToggleSwitch` (pending until the server answers), the address rows (Remove address as icon button, Add address), the discovered origins and the existing Save and remove confirmations. Failed saves keep the draft.
- Loading, load-error, empty and no-match states stay distinct. Pending requests stay inside the owning panel.

## Tests

- Per app: add `*Nav.test.ts` and `*Header.test.ts` (permissions and order, current page, shortcuts without the app itself, Profile with no Ember link, notification rows and empty state, Escape focus return), `OverviewView.test.ts` (counts, unreachable banner, Unavailable on failure), and update every `*View.test.ts` to the new markup. Add per changed page only the cases that cover new logic: search keeping a draft, the row opener, discard without a write, a failed save keeping the draft, `ToggleSwitch` replacing a checkbox. Update `router/pages.test.ts`, `guard.test.ts` and `index.test.ts` for the Overview landing page. Stronghold gets a `pages.test.ts` case that Analytics is listed for an account holding only `traffic.view`.
- Keep `radiusScale.test.ts`. Copied component tests (`RecordDrawer`, `PanelHelp`) run in each app.
- Add `e2e/` Playwright specs per app on the Treasury pattern: built app, fake API through `page.route` recording unexpected requests. One spec for the shell (sidebar at 1280, 768 and 375, Profile theme persisted, Escape focus), one for all pages at desktop, tablet and mobile in both themes (no horizontal page scroll, no unexpected request), one for a drawer (expand, restore, own-body scroll, footer reachable, discard). Spare ports: Armory 5198, Stronghold 5197 (`ARMORY_E2E_PORT`, `STRONGHOLD_E2E_PORT` override).
- Update both `AGENTS.md` files and the shared-component list in the frontend skill.

## Acceptance

- Every page renders real data with one page title. Keyboard, mouse and touch can navigate, search, open rows, resize drawers, confirm or discard and return focus.
- Parity with Portcullis, Legion and Treasury at desktop, 768px, 767px and 375px in Light and Dark for the shell, last-row hover and focus, search and drawers.
- Shared component copies match Treasury's except for app names. No checkbox outside acknowledgements. No hex or literal radius outside `style.css`. No reduced-motion code.
- Analytics shows in Stronghold's nav for an account that holds any of its permissions.
- No change to API clients, permissions, storage keys, schema, runtime dependencies or deployment. New route in each app: `/overview`. The only added package is `@playwright/test` as a dev dependency. The `@vitejs/plugin-vue` pin stays.

## Out of scope

Backend changes, new settings, a Profile or Settings page in either app, config-issue notifications, and the Ember web app.
