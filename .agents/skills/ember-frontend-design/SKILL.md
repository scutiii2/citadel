---
name: ember-frontend-design
description: Use when designing, building, restyling, or reviewing Citadel's Ember desktop or admin UI, including app shells, searchable panels, record rows, and editor drawers.
---

# Citadel frontend design

Use `ember-design-system` for tokens, radius, focus, and interaction rules. Use the target app's `AGENTS.md` for routing, permissions, and API conventions. Treat `apps/ember_web` as reference material for Ember patterns.

Reuse the target app's components and tokens before adding styles.

**Mobile and responsive work:** read [mobile-ui.md](mobile-ui.md) before changing narrow layouts, touch controls, keyboard behavior, sheets or mobile navigation, and when reviewing those interactions. It adds mobile acceptance checks to this skill and the existing design system. Its shared usability rules also apply to the affected desktop flow.

## 1. Pick the app

| Page is for | App |
|---|---|
| User-facing chat and tools | `apps/ember` |
| Staff accounts, roles, and invites | `apps/portcullis_admin` |
| Agents, gateway connections, MCP servers, and tuning | `apps/legion_admin` |
| Admin pages owned by Armory, Stronghold, or Treasury | The corresponding `apps/*_admin` app |

Use the target app's permission rules for admin routes. Portcullis enforces permissions server-side.

## Admin design reference

Use the [Legion Admin mockup](../../../apps/legion_admin/mockups/legion-redesign.html) and [Portcullis Admin mockup](../../../apps/portcullis_admin/mockups/portcullis-redesign.html) for admin shells, panels, and drawers. Apply these patterns to both apps, including the existing Legion profile menu and tuning toolbar when implementing these revisions. Reuse the target app's components and permissions.

### Shell

- Use Ember orange as the primary accent and keep Dark, Light, and System theme choices. The reference mockup opens in Dark mode.
- Use a compact full-width header. Put the sidebar toggle, app identity, thin vertical divider, and current page title on the left. Put Notifications, Help, and Profile on the right. Theme and Log out belong inside Profile.
- Use a labeled Dark, Light, and System theme selector with token-rounded corners, a chevron, and one inset focus outline.
- Keep cross-app shortcuts at the bottom of the sidebar. Use labels in the expanded desktop sidebar and named icons in the collapsed rail. On mobile, the header toggle reveals navigation above the content.
- Keep `PageLayout` for content geometry and scrolling. Use the header as the single visible page title and omit the generic subtitle from the body. Keep task-specific section headings.

### Panels and rows

- Put a labeled search at the right of roster, connection, and settings panel headers. Filter only that panel. Keep drafts when rows are filtered, and validate pending fields even when search hides them.
- Put labeled Cancel × and Save icons immediately left of search, in that order. Show both while edits differ from saved values and reserve both slots when clean. Confirm before discarding. Return focus to search when the icons disappear after Save or Discard.
- Give the search wrapper one inset focus outline around the icon and input. Suppress the inner input outline so focus has one visible indicator.
- Make the whole row open details when it has no dedicated details control. Use one native opener and a row-wide focus indicator. Preserve table semantics and independent row actions.
- Keep hover, selection, and focus paint inside token-rounded panel bounds. Clip paint at the panel edge and draw clipped focus rings inward. Keep wide tables in a separate local scroller. Check the last row in both themes.
- In Legion, group model gateways and MCP servers under **Connections**. Give both sections the same name, description, and URL row layout. Reuse one drawer pattern for editing description and URL.

### Drawers

- Admin panels use drawers, not modals, for anything opened from a panel: record details, editors, panel-level settings (Legion's Shared prompts), forms, create flows. Wrap `RecordDrawer` (Legion) rather than `BaseModal`. The only modal left is `ConfirmModal`, for a save, discard or delete question raised from inside a drawer.
- Open record details and editors in a full-height drawer anchored to the right edge. Keep the originating list visible behind a dimmed backdrop. Reuse `BaseModal` in `side` mode as the base, as in Portcullis Admin's Accounts panel.
- Put a labeled Edit icon immediately beside Expand and Close in the header. Expand to about 90% of viewport width, and let the same control restore the default width. Keep the record, draft, and scroll position when resizing.
- Edit inside the same drawer. Keep Save and Cancel in a persistent footer outside the scrolling form. Validate before opening save confirmation. Confirm discard on Cancel, Close, Escape, or backdrop dismissal while editing. Dismissing confirmation keeps the draft open. Closing details returns focus to the opener.

## 2. Shared base

- Both `style.css` files hold the same tokens (admin's also sets `:focus-visible`). Change a token in **both** or the apps drift.
- Every page view uses `PageLayout`; chat and auth screens are exempt. The enforced exemption list is `ChatView`, `LoginView`, `ConnectView`, `RegisterView`, `VerifyEmailView`, `NoAccessView`, `SharedChatView`, `ConfigIssuesView`, and the headerless `AdminView` route shell. Each routed child of `AdminView` owns its layout; the shell adds no column padding.
- `PageLayout` owns view scrolling, shared geometry, and the `actions` and `toolbar` slots. Its standard header provides the title and optional description on shells that delegate their heading to the view. Use `wide` for full-width pages and `fill` for workspace panels that scroll their own lists. Use the target app's `pageLayout.css` and preserve existing `info-content` where needed.
- Components exist in **both** apps as copies: `PageLayout`, `BaseModal`, `ConfirmModal`, `ToggleSwitch`, `SegmentedControl`, `SettingRow`, `ActionButton`, `CopyButton`, `DeleteButton`, `AuthCard`, `EmberLogo`, `AccountMenu`, `UsageHeatmap`, `ToolRunForm`, `IntegrationToolsModal`, `SidebarEditor`. The admin apps also keep identical copies of `ThemeSelect`, `AdminSearch`, `RecordDrawer`, `StatusFilters` (the segmented filter bar), `DraftActions` (the reserved Cancel × and Save slots), `PanelHelp`, `StatTile` and the `useDraftPanel` composable, in Portcullis, Legion and Treasury (Armory and Stronghold admin follow later). A fix to one needs the same fix in the other; say so in the proposal.
- `ConfirmModal` lives in `components/ui/dialogs/` (web) and `components/admin/` (admin). Never call native `confirm()`.
- Admin extras: `StatTile`, `*Panel`, `*Drawer`, `TicketBoard`, `RoleEditor`.

Before writing a component, grep both `components/` folders for an existing one.

## Shared pieces: always use these, never re-style them per page

These live in `ember_web` only (not copied to admin). A page that needs one of these patterns uses the component; it does not write its own markup or CSS for it. If the component lacks something, extend the component (a prop or slot) rather than forking it in the page. Pages add only layout tweaks through their own class (spacing, alignment).

| Pattern | Use | Where |
|---|---|---|
| Selectable row in a list pane (notes, memories, tickets, documents) | `ListRow` (`active` sets highlight and `aria-current`; optional `actions` slot encloses separate controls in the same selected frame) | `components/ui/lists/` |
| Search box with magnifier; a trailing button or sort menu goes in its slot | `SearchField` (`v-model`, `label`) | `components/ui/lists/` |
| Loading, load-error with retry, empty state | `StateMessage` (`kind`: `loading`, `error`, `empty`) | `components/ui/status/` |
| Red-outlined delete row at the end of an editor or dialog | `DangerZone` (the button still opens a `ConfirmModal`) | `components/ui/status/` |
| "12/200" counter under a text field | `CharacterCount` | `components/ui/status/` |
| "Files are kept for N hours" note | `RetentionNote` | `components/ui/status/` |
| "‹ All X" back button shown below 768px | `BackButton` (`ghost` for the text look) | `components/ui/buttons/` |
| Narrow-viewport (under 768px) flag in a page script | `useNarrow()` | `composables/` |
| Any dialog (never a hand-written `<dialog>`) | `BaseModal` (`open`, `title`, `@close`; Esc, × and backdrop all emit `close`) | `components/ui/dialogs/` |
| Cancel / Save pills in a dialog | classes `pill-btn primary` and `pill-btn ghost` (global, in `style.css`) | `style.css` |
| Dropdown or popover that closes on a press outside | `useOutsideClose(root, open, close, event?)` (Esc and focus stay in the component) | `composables/` |
| Leaving a page with unsaved edits asks first (route change and tab close) | `useUnsavedGuard({ dirty, busy?, allow? })`; bind the page's `ConfirmModal` to its `open` and `answer` | `composables/` |
| Reorder a list by drag and Alt + arrow keys | `useReorder({ move, count, keys })`; bind its handlers to each item | `composables/` |
| "2 KB" / "1 file" text | `formatBytes`, `plural` | `utils/format.ts` |
| Quiet text button in a dialog or popover ("Edit", "Retry") | classes `link-btn` (+ `danger`), global in `style.css` | `style.css` |
| Stacked labelled fields in a dialog | class `dialog-form` on the `<form>`, global in `style.css` | `style.css` |
| Small outlined "Off for everyone" / "On" pill | class `status-badge`, global in `style.css` | `style.css` |
| Per-browser setting that survives blocked storage | `readStored(key)` / `writeStored(key, value)` | `utils/browser/storage.ts` |
| Textarea that grows with its text | `growToContent(textarea)` | `utils/browser/autoGrow.ts` |
| Where a menu opens: under a button or at the pointer | `pointBelow(button)` / `pointAt(event, button)` | `components/ui/menus/menuPoint.ts` |
| Text only for screen readers | class `sr-only` (global, in `style.css`); never a local copy | `style.css` |
| Busy spinner on a button | just set `aria-busy`; `style.css` draws the ring, so add no local `::before` or keyframes | `style.css` |
| List pane plus editor with Save | `ListEditorLayout` (`actions` slot adds a footer control; `visibleScrollbars` opts the editor into visible scrolling) | `components/layout/` |
| Visible independent workspace scrollbar | `pane-scroll` on the list scroller; `ListEditorLayout visibleScrollbars` on the editor | `components/layout/pageLayout.css` |
| Two panes or a stacked workspace | `WorkspaceLayout` | `components/layout/` |

Rules:
- Do not add a page-local `.empty`, `.load-error`, `.danger-zone`, `.character-count`, `.retention`, `.back` or search-box style. Do not call `window.matchMedia` for the narrow check.
- The base styles of `ListRow` have no specificity, so a page restyles a row with its own class; do not use `!important`.
- When reviewing or touching a page that still has a hand-written copy of one of these, replace it with the component in the same change.
- A new pattern that appears on a second page becomes a component in `components/ui/` with a unit test, and gets a row in this table.


## Task-focused layouts

These are the user's preferred Ember patterns. Choose the shape that fits the task; retain the page's supported actions and data contracts.

- **Hierarchy:** give the active task one clear primary action. Keep metadata quiet and move occasional setup, publishing, and management controls into labeled accordions, dialogs, or secondary modes. Keep progress and results easy to find.
- **Desktop workspaces:** pair a working area with a useful companion pane, such as a note list, folder browser, or temporary files. Use `PageLayout wide fill` when the panes should own their scrolling; keep `min-width: 0` and `min-height: 0` through the flex/grid chain.
- **Mobile modes:** below 768px give the active task the full width. Use list-to-editor navigation with a visible Back action, or a small segmented mode selector. Preserve reachable Save/download actions, readable text, and 44px touch controls. Put sheets above `--rail-height`.
- **Lists:** use readable rows with light separators, short secondary metadata, and one clear contextual action. Follow the admin drawer pattern for record details and editing. Place deletion in its final Danger zone with confirmation.
- **List/editor workspaces:** match Memory and Notes structurally: compact searchable list, readable titles, document-style editor, collapsed tools and management, persistent Save, and mobile Back. Move focus into the editor on entry and restore it to the originating row (or search) on return. Keep group explanations once beneath headings and usage counts secondary. Use the shared scrollbar opt-in when requested, with search and Save outside scrolling bodies.
- **Row actions:** use `ListRow`'s `actions` slot for secondary actions such as Approve on Ember workspaces. Follow the admin row pattern for tables and rosters.
- **Browser/reader workspaces:** keep the scope switch and search inside the browsing sidebar, above breadcrumbs or search results, as Brains does. Use the same pane spacing, row selection and scrollbar utility as Skills. Keep source setup and path controls in labeled disclosures; the main pane is for reading, with its audience and read-only state visible. Search and status checks preserve the current reader. Mobile Back restores focus to the originating row or search. Keep connection dialogs mounted outside the sidebar so drafts and open dialogs survive a viewport change.
- **Notes search:** for a fully loaded note list, filter saved titles, full text and tags locally without changing its ordering. Search only changes the list: keep the open editor, new-note draft and publishing panel alive, including when no notes match. Use `StateMessage` with a clear-search action for no results. Let note text grow through `growToContent` so the editor pane owns scrolling; keep each secondary tool in its own disclosure on mobile as well as desktop.
- **State:** keep draft-bearing panels and job watchers mounted when changing modes. Place dialogs outside hidden tab ancestors. Refreshing status must preserve the current document/result. Clear private content before changing scopes, and open search hits in their originating scope.
- **Real data:** render the formats, sizes, expiry, scope, and status returned by the API. Clearly label sample data in mockups; keep production previews honest when thumbnails or estimates are unavailable.

Use these existing pages as implementation references:

| Task | Reference under `apps/ember_web/src/` |
|---|---|
| Writing with secondary tools | `features/notes/NotesView.vue`: draft-safe sidebar search, growing document editor, individual tool disclosures and persistent Save |
| Reviewing short facts | `features/memory/MemoryView.vue`: searchable list/editor workspace, mobile Back, guarded drafts and management disclosure |
| Reviewing proposed how-tos | `features/skills/SkillsView.vue`: grouped list/editor workspace, approval inside the selected row, document fields, visible pane scrollbars |
| Reading durable documents | `features/brains/BrainsView.vue`: sidebar-owned scope/search, persistent reader, visible pane scrollbars, collapsed source settings |
| Downloading and collecting media | `features/mediaDownloader/MediaDownloaderView.vue`, `features/mediaDownloader/components/`: single-link flow, ZIP groups, temporary files |

## 3. Navigation placement

- **ember_web rail** (`NavRail.vue`): header = Overview (wordmark) + Chat. Main list = only pages backed by a dedicated mcp_server capability (Notes, Memory, Generator, Tickets). Every other page (Capabilities, Agents, Usage, Settings, Profile) goes in `AccountMenu.vue`.
- **Admin navigation:** use the target app's page registry, permission filtering, and navigation preferences where supported. Use the approved admin shell as the design reference.
- On existing shells with a mobile bottom rail, use `bottom: var(--rail-height)` for sheets above that rail.

## 4. Rules that cost us before

- Every panel header carries a `PanelHelp` icon first among its tools: a click opens a popover saying what the panel is for. Add it to each new panel.
- No checkboxes in admin panels, drawers or settings: an on/off or a choice from a list is a `ToggleSwitch` (a `small` one in dense lists). A checkbox is only for a form acknowledgement or checklist, such as agreeing to a policy or confirming something was read.
- Radius only via `--radius-*`, colour only via tokens. `radiusScale.test.ts` in each app fails on a literal radius.
- Scoped CSS that a parent page also styles: use the more specific selector (`button.delete-button`).
- A switch that calls the server stays pending until the server answers; never show unconfirmed state. Browser-local settings apply instantly ("Applies instantly. Saved on this device."); settings that reach other accounts are a draft with an unsaved bar and Save.
- Destructive: red-outlined pill in a Danger zone last in the form; severe ones use `requireText`.
- Keep admin-only pages in the admin app that owns their domain.
- No reduced-motion setting, media query or test. Animations always play.
- Status needs icon + text, not colour alone.

## Brain UI/UX checks

Distilled from `Brain/Maps/UI UX Frontend Rulesets.md` (consult it for rationale when available). These supplement the rules above; the no-reduced-motion rule and other project rules win on conflict.

- **Forms:** ask only for what the task needs. Use the right `type`, `autocomplete` and `inputmode`; allow paste. Validate on blur or submit, not while the user is still typing a valid value. Put the error beside its field, tie it to the control (`aria-describedby`, `aria-invalid`) and keep entered values.
- **Contrast:** test real foreground/background pairs, including hover, focus and tinted `color-mix` fills: 4.5:1 for text, 3:1 for large text and UI boundaries. Check hierarchy in grayscale before relying on hue.
- **Semantics:** links for destinations, buttons for actions. Tabs that swap panels need tab semantics and arrow-key behaviour, not link markup. A popover or tooltip is not a modal: no focus trap, no scroll lock. A tooltip supplements a label, never replaces it.
- **Decoration:** glow, glass, shine, neon and gradients sit on their own layer with `pointer-events: none`. They must not cover controls, change reading order or clip focus outlines, and need a readable plain fallback. Keep them optional; prefer existing tokens.
- **Scroll:** the view scrolls, not the page. Sticky headers must not cover focused fields or eat a small viewport. Prefer pagination or Load more over infinite scroll when users need a stable position or a reachable footer; keep position, loading and error states. A wide track or table is a labeled local scroller reachable by keyboard.
- **Auto-moving content:** anything that moves by itself for over 5 seconds beside other content (marquee, carousel, ticker) needs a visible pause/stop control; hover-only pause is not enough. Hide decorative duplicates from assistive tech.
- **Design-law prompts:** proximity (does spacing show grouping?), Von Restorff (does the standout element deserve it?), Hick (group or reveal choices progressively without hiding needed ones), Jakob (does it behave like the familiar pattern?). Prompts, not numeric caps.

## 5. Workflow

1. Use the approved design and scope already in the conversation. Implement an approved mockup when asked to proceed. When the layout is undecided, propose a concrete design with the files, reused components, and any dependencies before implementation.
2. Implement with existing components; copy shared-component changes to both apps.
3. Run `pnpm exec vue-tsc -b` and the nearest relevant tests for the touched app. Include `radiusScale.test.ts` when changing radius or layout styles. Follow the workspace testing budget.
4. Verify affected UI states in the browser when available. Use sample data or a fake `/api` for previews and isolate browser preferences from production.
5. Check desktop, 768px, 767px, and 375px in Light and Dark. For admin panels, verify the last row's hover and focus corners and dirty/clean header geometry. For drawers, verify expand, shrink, scroll, confirmation, and focus return.

## Review checklist

- [ ] Page belongs to the app that owns its domain
- [ ] Existing component reused; copies updated in both apps
- [ ] Rows, search, loading/error/empty, danger zone, counters, retention and back buttons use the shared pieces table, no page-local copies
- [ ] No hex or literal radius outside `style.css`
- [ ] Nav entry follows section 3
- [ ] Confirm modal / Danger zone for destructive actions
- [ ] Focus ring, accessible name, `aria-busy` on busy controls
- [ ] No horizontal page scroll at 375; page itself never scrolls, the view does
- [ ] Main task, key info and primary action obvious; secondary actions lighter
- [ ] Related items grouped by spacing; repeated components share padding
- [ ] Text and UI contrast checked in light and dark, including hover/focus
- [ ] Form asks only what is needed; errors beside fields, values kept
- [ ] Links vs buttons vs tabs semantics correct; popovers not trapped as modals
- [ ] Decoration non-blocking with a readable fallback; auto-moving content has pause/stop
- [ ] Type check and focused tests pass
