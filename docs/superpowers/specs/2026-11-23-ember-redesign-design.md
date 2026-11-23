# Ember redesign specification

Bring the Ember Windows/browser app (`apps/ember`) to the panel, drawer and control patterns of the redesigned admin apps ([Portcullis](2026-11-23-portcullis-admin-redesign-design.md), Legion, [Treasury](2026-11-23-treasury-admin-redesign-design.md), [Armory and Stronghold](2026-11-23-armory-stronghold-admin-redesign-design.md)). Follow the [Citadel frontend skill](../../../.agents/skills/ember-frontend-design/SKILL.md) and its [mobile guide](../../../.agents/skills/ember-frontend-design/mobile-ui.md). Shared components stay identical copies; Treasury Admin holds the newest ones, so copy from `apps/treasury_admin` (or Armory for `SettingsPanel`). `ember_web` stays reference only and is not changed.

## Today

Ember is the user-facing app: Chat, Capabilities, Agents, Usage, Notes, Skills, Shares, Global, Generator, PDF merger, Media downloader, Tickets, Settings and Profile, plus Overview. Navigation is a left rail on desktop (user can pin, reorder and hide pages) and a bottom tab bar below 768px. It already has the shared `PageLayout`, `BaseModal`, `ConfirmModal`, `ToggleSwitch`, `SegmentedControl`, `ListRow`, `SearchField`, `StateMessage` and `ToolRunForm`. It has none of `PanelHelp`, `RecordDrawer`, `AdminSearch`, `StatusFilters`, `DraftActions`, `StatTile`, `SettingsPanel`, `useDraftPanel`. No e2e specs.

Gaps against the admin design:
- Eighteen files open a `BaseModal` from a page or panel (Agents, Capabilities, Tickets, Global, Shares, PDF merger, Media downloader and others).
- Pages describe themselves in a body paragraph; no panel has a help popover.
- Panel header actions are text buttons; settings pages save with a text Save and no dirty-gated draft actions.
- Four checkboxes remain that are not acknowledgements or selection: `TriageQuestionModal` ("details"), `ProposalsDialog` ("remove items"), plus the two bulk-select boxes in chat (`ChatRow`, `ConversationSidebar`).
- `ToolRunForm` boolean widget was already converted to `ToggleSwitch` (done before this spec).

## What stays Ember

Ember is not an admin app. Keep:
- The rail, the bottom tab bar, pin/reorder/hide, the wordmark, the account menu, the ticket unread badge and the Windows-app connect flow. No header or sidebar replacement, no Notifications or Help header buttons.
- Chat and everything inside it: the conversation list, composer, message rows, and chat-scoped dialogs (`ShareDialog`, `TemplatesModal`, `FolderDialogs`, `TriageQuestionModal`, attachment preview). Chat is exempt from the panel rules and its dialogs stay modals, because they interrupt a turn in progress and are not opened from a panel.
- The list/editor workspaces of Notes, Skills, Shares and Global (`ListEditorLayout`, `ListRow`, `SearchField`, mobile Back). `SearchField` stays Ember's search box; do not add a second search component.
- Current permissions, routes, API clients and stores.

## Rules adopted from the admin apps

- **Drawers, not modals** for anything opened from a page or panel: record details, editors, forms, tool runs, create flows. Use `RecordDrawer` (copy of Treasury's, wraps `BaseModal side`): Edit, Expand and Close in the header, Save and Cancel in a persistent footer, discard confirmation on Cancel, Close, Escape and backdrop while dirty, focus back to the opener. `ConfirmModal` is the only modal left outside chat.
- **Panel headers.** Each page's main panel gets `PanelHelp` first among its tools; the old body description and static hints move into its popover. Other header actions are icon buttons (`admin-icon`, `accent` for the primary one) with `aria-label` and `title`. Pages keep their one `h1` (Ember has no header title bar, so `PageLayout`'s title stays visible).
- **No checkboxes** except acknowledgements, checklists and multi-select of list rows. `TriageQuestionModal` and `ProposalsDialog` keep their checkboxes only if they are acknowledgements; convert them to `ToggleSwitch` if they are on/off options (decide per file when implementing, and record it in the task). The chat bulk-select boxes stay (list selection).
- **Drafts.** Settings and Profile use `SettingsPanel`, `DraftActions` and `useDraftPanel`: Cancel and Save slots shown only while dirty, discard confirmed, focus to search, search hides fields only and never drops a draft.
- **Primary buttons** are rounded rectangles (`--radius-md`); links styled as buttons have no underline. Radius and color only through tokens, no reduced-motion code, switches that call the server stay pending until it answers.
- **Copy, do not share.** Copy `PanelHelp`, `RecordDrawer`, `DraftActions`, `StatTile`, `StatusFilters`, `SettingsPanel`, `AdminSearch` (only where a page has no `SearchField` use), `useDraftPanel` and `admin.css` with their tests into `src/components/ui/panel/` (new folder, Ember has no `components/admin`), and the admin block of `style.css` the copies need. Fix `PanelHelp`'s no-glow style as in the other copies.

## Pages

- **Overview.** Keep the existing page list. Add `StatTile`s only for data existing clients return and only for pages the account may open: Tickets (open or unread), Agents (running of total), Capabilities (online of total), Usage (period tokens). A failed count shows Unavailable, never zero. Keep the one-line page descriptions; they come from `NAV_PAGES`.
- **Settings.** One `SettingsPanel` with `PanelHelp`, `DraftActions` and a search over section titles. Sections hidden with `v-show`. Keep every preference, its reset, the admin-only tool-approval section and the immediate-apply behavior of browser-local settings ("Applies instantly. Saved on this device." stays; those controls are not part of the draft).
- **Profile (Account).** Same: `SettingsPanel` for name, email, password and sessions where they are a draft; destructive actions keep their Danger zone and `ConfirmModal`.
- **Capabilities.** Roster panel with `PanelHelp`, `StatusFilters` (All, Online, Offline), `SearchField`, icon Refresh. A row opens a `RecordDrawer` with its tools and resources. Replace `ToolRunModal`, `CommandFormModal` and `UserExtensionModal` with drawers. Extensions (other MCP servers) keep add, edit and remove with a `ConfirmModal`.
- **Agents.** Roster panel with `PanelHelp` and `SearchField`; the agent details modal becomes a drawer. Entry agent and status unchanged.
- **Usage.** Panel header with `PanelHelp`, the period `SegmentedControl` and an icon Refresh; account detail and export as in Stronghold's Usage if a drawer is needed, otherwise unchanged.
- **Tickets.** `PanelHelp`, status filters as `StatusFilters`, `SearchField`, icon New ticket (accent). The ticket thread and the new-ticket form open in `RecordDrawer` (replacing the `BaseModal` use in `TicketsView.vue`). Unread badge and `tickets-seen` event unchanged.
- **Notes, Skills, Shares, Global.** Keep the workspace layouts. Add `PanelHelp` to each list or reader header; move descriptions into it. Replace the dialogs opened from these pages (`GlobalFileDialog`, `GlobalReview`, `GlobalSkills`, `ShareDialog` and `ShareReview` under sharing) with drawers. Dialogs that ask only yes/no stay `ConfirmModal`.
- **Generator, PDF merger, Media downloader.** `PanelHelp` in each tool panel header, icon actions where the header has text buttons, and the `BaseModal` uses in `PdfMergerView.vue` and `MediaDownloaderView.vue` become drawers. Job, download and file behavior unchanged.

## Tests

- Add `PanelHelp.test.ts` and `RecordDrawer.test.ts` (copied). Update each touched `*View.test.ts` to the new markup (drawer opener names `Open X`, dirty-gated Save, `PanelHelp` present). Add cases only for new logic: a settings draft surviving a search, discard confirmation without a write, a failed save keeping the draft, a switch staying pending.
- Keep `architecture.test.ts`, `pageLayout.test.ts`, `radiusScale.test.ts` and `themeContrast.test.ts` green; extend `architecture.test.ts` if it lists allowed `BaseModal` importers, so only chat dialogs and `RecordDrawer` may import it.
- Add `e2e/` Playwright on the Treasury pattern (`@playwright/test`, Chrome channel, built app via `vite build && vite preview`, fake API through `page.route` recording unexpected requests). Specs: all pages at 1280, 768 and 375 in both themes (no horizontal page scroll, no unexpected request), one drawer (expand, restore, own-body scroll, footer reachable, discard confirmation, focus return). Port: the next free in `26500–26999`, `EMBER_E2E_PORT` overrides it; do not reuse 26506.
- Update `apps/ember/AGENTS.md` (admin rules that apply, the copy list) and the shared-component list in the frontend skill.

## Out of scope

Chat internals, the Tauri shell, `ember_web`, rail and tab-bar behavior, new pages, API changes.
