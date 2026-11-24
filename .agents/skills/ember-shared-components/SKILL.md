---
name: ember-shared-components
description: Use before writing any Citadel Vue component or page-local CSS. Lists the shared components, composables, utils and global classes in apps/ember and the admin apps (PageLayout, BaseModal, ListRow, SearchField, StateMessage, DangerZone, useOutsideClose, and others) and the rule to reuse them instead of re-styling.
---

# Citadel shared components

Reuse before adding. Grep both `components/` folders for an existing one.

## Shared base

- Both `style.css` files hold the same tokens (admin's also sets `:focus-visible`). Change a token in **both** or the apps drift.
- Every page view uses `PageLayout`; chat and auth screens are exempt. The enforced exemption list is `ChatView`, `LoginView`, `ConnectView`, `RegisterView`, `VerifyEmailView`, `NoAccessView`, `SharedChatView`, `ConfigIssuesView`, and the headerless `AdminView` route shell. Each routed child of `AdminView` owns its layout; the shell adds no column padding.
- `PageLayout` owns view scrolling, shared geometry, and the `actions` and `toolbar` slots. Its standard header provides the title and optional description on shells that delegate their heading to the view. Use `wide` for full-width pages and `fill` for workspace panels that scroll their own lists. Use the target app's `pageLayout.css` and preserve existing `info-content` where needed.
- Components exist in **both** apps as copies: `PageLayout`, `BaseModal`, `ConfirmModal`, `ToggleSwitch`, `SegmentedControl`, `SettingRow`, `ActionButton`, `CopyButton`, `DeleteButton`, `AuthCard`, `EmberLogo`, `AccountMenu`, `UsageHeatmap`, `ToolRunForm`, `CapabilityDrawer`, `SidebarEditor`. The admin apps also keep identical copies of `ThemeSelect`, `AdminSearch`, `RecordDrawer`, `StatusFilters` (the segmented filter bar), `DraftActions` (the reserved Cancel × and Save slots), `PanelHelp`, `StatTile`, `SettingsPanel` (a settings page as one panel; Armory and Stronghold) and the `useDraftPanel` composable, in all five admin apps; Ember keeps the same copies (without `ThemeSelect`) in `src/components/ui/panel/`. A fix to one needs the same fix in the other; say so in the proposal.
- `ConfirmModal` lives in `components/ui/dialogs/` (web) and `components/admin/` (admin). Never call native `confirm()`.
- Admin extras: `StatTile`, `*Panel`, `*Drawer`, `TicketBoard`, `RoleEditor`.
- Drawer forms with more than a handful of fields split into tabs with `FormTabs` (`components/admin/`, copied into `legion_admin`, `stronghold_admin` and `treasury_admin`; copy it to another admin app before using it there). The form keeps every panel mounted with `v-show`, panels use `role="tabpanel"`, `id="<prefix>-panel-<id>"` and `aria-labelledby="<prefix>-tab-<id>"`, errors and test results sit outside the panels, and the form returns to the first tab when a record opens. An item can be `disabled` with a `title` saying why. Forms of two or three fields stay a single page.

Before writing a component, grep both `components/` folders for an existing one.

## Shared pieces: always use these, never re-style them per page

These live in `apps/ember` only (not copied to admin). A page that needs one of these patterns uses the component; it does not write its own markup or CSS for it. If the component lacks something, extend the component (a prop or slot) rather than forking it in the page. Pages add only layout tweaks through their own class (spacing, alignment).

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


