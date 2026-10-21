---
name: ember-frontend-design
description: Use when designing, building, restyling or reviewing any screen, component or layout in ember_web or ember_admin (the two Vue 3 apps in apps/Ember/). Covers which app a page belongs in, the shared tokens and components to reuse, page layout, navigation placement, confirmations, settings behaviour, the radius test and how to check a UI. Use even for small visual tweaks ("make this card nicer", "add a settings row", "fix the spacing on the tickets page").
---

# Ember frontend design (ember_web + ember_admin)

Project-specific layer on top of `ember-design-system` (tokens, radius scale, focus, motion, interaction rules). Read that skill for the visual rules; this one says how to apply them in these two apps. For routes, stores and API wiring use `ember-feature-scaffold`.

**Core idea:** one product, two apps. Reuse before writing. Pick tokens and a pattern first, write styles second.

## 1. Pick the app

| Page is for | App |
|---|---|
| Every signed-in user, chat, capability tools (Notes, Memory, Generator, Tickets as a user) | `ember_web` (port 5173) |
| Staff: accounts, roles, invites, agents, capabilities, analytics, ticket triage, workspace settings | `ember_admin` (port 5176) |

Gate admin pages by permission in `ember_admin/src/router/pages.ts`; the guard is cosmetic, ember_api enforces.

## 2. Shared base

- Both `style.css` files hold the same tokens (admin's also sets `:focus-visible`). Change a token in **both** or the apps drift.
- Every page view uses `PageLayout`; chat and auth screens are exempt. The enforced exemption list is `ChatView`, `LoginView`, `RegisterView`, `VerifyEmailView`, `NoAccessView`, `SharedChatView`, `ConfigIssuesView`, and the headerless `AdminView` route shell. Each routed child of `AdminView` owns its layout; the shell adds no column padding.
- `PageLayout` owns the title, optional description, `actions` and `toolbar` slots, and view scrolling. Use `wide` for full-width pages and `fill` for workspace panels that scroll their own lists. Header geometry and typography live only in `ember_web/src/components/pageLayout.css` (admin imports it by relative path). Admin panel content styles stay in `adminPages.css` and `admin.css`. Existing information pages retain `info-content` to opt into `infoPage.css` body decorations; adding PageLayout alone must not restyle page content.
- Components exist in **both** apps as copies: `PageLayout`, `BaseModal`, `ConfirmModal`, `ToggleSwitch`, `SegmentedControl`, `SettingRow`, `LockSwitch`, `ActionButton`, `CopyButton`, `DeleteButton`, `AuthCard`, `EmberLogo`, `AccountMenu`, `UsageHeatmap`, `ToolRunForm`, `IntegrationToolsModal`, `SidebarEditor`. A fix to one needs the same fix in the other; say so in the proposal.
- `ConfirmModal` lives in `components/` (web) and `components/admin/` (admin). Never call native `confirm()`.
- Admin extras: `StatTile`, `*Panel`, `*Drawer`, `TicketBoard`, `RoleEditor`.

Before writing a component, grep both `components/` folders for an existing one.

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
| Writing with secondary tools | `views/NotesView.vue`: list/editor, collapsed tools, persistent Save |
| Reviewing short facts | `views/MemoryView.vue`: searchable rows, editor dialog/mobile sheet |
| Reading durable documents | `views/BrainsView.vue`: scoped search, browser/reader, secondary connection settings |
| Downloading and collecting media | `views/VideoDownloaderView.vue`, `components/videoDownloader/`: single-link flow, ZIP groups, temporary files |

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

## 5. Workflow

1. Use the approved design and scope already in the conversation. Implement an approved mockup when asked to proceed. When the layout is undecided, propose a concrete design with the files, reused components, and any dependencies before implementation.
2. Implement with existing components; copy shared-component changes to both apps.
3. Check: `npx vue-tsc -b`, `npm test` (includes `radiusScale.test.ts`), `npm run test:e2e` in the touched app. Web e2e uses `e2e/fakeApi.ts`; click a switch's label, not its hidden checkbox.
4. Do not spawn browser-verification agents; the user tests manually. If a visual check is needed, use a throwaway Vite config with a fake `/api` and clear `localStorage` first (theme persists per origin).
5. Test widths: desktop, 768, 375, light and dark.

## Review checklist

- [ ] Right app; admin-only page not in ember_web
- [ ] Existing component reused; copies updated in both apps
- [ ] No hex or literal radius outside `style.css`
- [ ] Nav entry follows section 3
- [ ] Confirm modal / Danger zone for destructive actions
- [ ] Focus ring, accessible name, `aria-busy` on busy controls
- [ ] No horizontal page scroll at 375; page itself never scrolls, the view does
- [ ] `vue-tsc`, `npm test` pass
