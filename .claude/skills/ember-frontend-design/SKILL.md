---
name: ember-frontend-design
description: Use when designing, building, restyling or reviewing any screen, component or layout in ember_web or ember_admin (the two Vue 3 apps in apps/Ember/). Covers which app a page belongs in, the shared tokens and components to reuse, page layout, navigation placement, confirmations, settings behaviour, the radius test and how to check a UI. Use even for small visual tweaks ("make this card nicer", "add a settings row", "fix the spacing on the tickets page").
---

# Ember frontend design (ember_web + ember_admin)

Project-specific layer on top of `ember-design-system` (tokens, radius scale, focus, motion, interaction rules). Read that skill for the visual rules; this one says how to apply them in these two apps. For routes, stores and API wiring use `ember-feature-scaffold`.

**Core idea:** one product, two apps. Reuse before writing. Pick tokens and a pattern first, write styles second.

**Mobile and responsive work:** read [mobile-ui.md](mobile-ui.md) before changing narrow layouts, touch controls, keyboard behavior, sheets or mobile navigation, and when reviewing those interactions. It adds mobile acceptance checks to this skill and the existing design system. Its shared usability rules also apply to the affected desktop flow.

## 1. Pick the app

| Page is for | App |
|---|---|
| Every signed-in user, chat, capability tools (Notes, Memory, Generator, Tickets as a user) | `ember_web` (port 5173) |
| Staff: accounts, roles, invites, agents, capabilities, analytics, ticket triage, workspace settings | `ember_admin` (port 5176) |

Gate admin pages by permission in `ember_admin/src/router/pages.ts`; the guard is cosmetic, ember_api enforces.

## 2. Shared base

- Both `style.css` files hold the same tokens (admin's also sets `:focus-visible`). Change a token in **both** or the apps drift.
- Every page view uses `PageLayout`; chat and auth screens are exempt. The enforced exemption list is `ChatView`, `LoginView`, `RegisterView`, `VerifyEmailView`, `NoAccessView`, `SharedChatView`, `ConfigIssuesView`, and the headerless `AdminView` route shell. Each routed child of `AdminView` owns its layout; the shell adds no column padding.
- `PageLayout` owns the title, optional description, `actions` and `toolbar` slots, and view scrolling. Use `wide` for full-width pages and `fill` for workspace panels that scroll their own lists. Header geometry and typography live only in `ember_web/src/components/layout/pageLayout.css` (admin imports it by relative path). Admin panel content styles stay in `adminPages.css` and `admin.css`. Existing information pages retain `info-content` to opt into `infoPage.css` body decorations; adding PageLayout alone must not restyle page content.
- Components exist in **both** apps as copies: `PageLayout`, `BaseModal`, `ConfirmModal`, `ToggleSwitch`, `SegmentedControl`, `SettingRow`, `LockSwitch`, `ActionButton`, `CopyButton`, `DeleteButton`, `AuthCard`, `EmberLogo`, `AccountMenu`, `UsageHeatmap`, `ToolRunForm`, `IntegrationToolsModal`, `SidebarEditor`. A fix to one needs the same fix in the other; say so in the proposal.
- `ConfirmModal` lives in `components/ui/dialogs/` (web) and `components/admin/` (admin). Never call native `confirm()`.
- Admin extras: `StatTile`, `*Panel`, `*Drawer`, `TicketBoard`, `RoleEditor`.

Before writing a component, grep both `components/` folders for an existing one.

## Shared pieces: always use these, never re-style them per page

These live in `ember_web` only (not copied to admin). A page that needs one of these patterns uses the component; it does not write its own markup or CSS for it. If the component lacks something, extend the component (a prop or slot) rather than forking it in the page. Pages add only layout tweaks through their own class (spacing, alignment).

| Pattern | Use | Where |
|---|---|---|
| Selectable row in a list pane (notes, memories, tickets, documents) | `ListRow` (`active` prop sets the highlight and `aria-current`) | `components/ui/lists/` |
| Search box with magnifier; a trailing button or sort menu goes in its slot | `SearchField` (`v-model`, `label`) | `components/ui/lists/` |
| Loading, load-error with retry, empty state | `StateMessage` (`kind`: `loading`, `error`, `empty`) | `components/ui/status/` |
| Red-outlined delete row at the end of an editor or dialog | `DangerZone` (the button still opens a `ConfirmModal`) | `components/ui/status/` |
| "12/200" counter under a text field | `CharacterCount` | `components/ui/status/` |
| "Files are kept for N hours" note | `RetentionNote` | `components/ui/status/` |
| "‹ All X" back button shown below 768px | `BackButton` (`ghost` for the text look) | `components/ui/buttons/` |
| Narrow-viewport (under 768px) flag in a page script | `useNarrow()` | `composables/` |
| List pane plus editor with Save | `ListEditorLayout` | `components/layout/` |
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
- **Lists:** use readable rows with light separators, short secondary metadata, and one clear contextual action. Use an editor/details dialog for occasional management and place deletion in its final Danger zone with confirmation.
- **State:** keep draft-bearing panels and job watchers mounted when changing modes. Place dialogs outside hidden tab ancestors. Refreshing status must preserve the current document/result. Clear private content before changing scopes, and open search hits in their originating scope.
- **Real data:** render the formats, sizes, expiry, scope, and status returned by the API. Clearly label sample data in mockups; keep production previews honest when thumbnails or estimates are unavailable.

Use these existing pages as implementation references:

| Task | Reference under `apps/Ember/ember_web/src/` |
|---|---|
| Writing with secondary tools | `features/notes/NotesView.vue`: list/editor, collapsed tools, persistent Save |
| Reviewing short facts | `features/memory/MemoryView.vue`: searchable rows, editor dialog/mobile sheet |
| Reading durable documents | `features/brains/BrainsView.vue`: scoped search, browser/reader, secondary connection settings |
| Downloading and collecting media | `features/mediaDownloader/MediaDownloaderView.vue`, `features/mediaDownloader/components/`: single-link flow, ZIP groups, temporary files |

## 3. Navigation placement

- **ember_web rail** (`NavRail.vue`): header = Overview (wordmark) + Chat. Main list = only pages backed by a dedicated mcp_server capability (Notes, Memory, Generator, Tickets). Every other page (Capabilities, Agents, Usage, Settings, Profile) goes in `AccountMenu.vue`.
- **ember_admin rail** (`AdminNav.vue`): pages from `ADMIN_NAV_PAGES`, filtered by permission, ordered by nav prefs. New admin page = entry in `router/pages.ts` with an icon path and permission.
- Below 768px the rail becomes a bottom bar of height `--rail-height`; sheets use `bottom: var(--rail-height)`.

## 4. Rules that cost us before

- Radius only via `--radius-*`, colour only via tokens. `radiusScale.test.ts` in each app fails on a literal radius.
- Scoped CSS that a parent page also styles: use the more specific selector (`button.delete-button`).
- A switch that calls the server stays pending until the server answers; never show unconfirmed state. Browser-local settings apply instantly ("Applies instantly. Saved on this device."); settings that reach other accounts are a draft with an unsaved bar and Save.
- Destructive: red-outlined pill in a Danger zone last in the form; severe ones use `requireText`.
- Admin and Analytics pages exist only in ember_admin. Do not copy them back to ember_web.
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
3. Check: `npx vue-tsc -b`, `npm test` (includes `radiusScale.test.ts`), `npm run test:e2e` in the touched app. Web e2e uses `e2e/fakeApi.ts`; click a switch's label, not its hidden checkbox.
4. Do not spawn browser-verification agents; the user tests manually. If a visual check is needed, use a throwaway Vite config with a fake `/api` and clear `localStorage` first (theme persists per origin).
5. Test widths: desktop, 768, 375, light and dark.

## Review checklist

- [ ] Right app; admin-only page not in ember_web
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
- [ ] `vue-tsc`, `npm test` pass
