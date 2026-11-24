---
name: ember-frontend-design
description: Use first when designing, building, restyling, or reviewing Citadel's Ember desktop or admin UI. Picks the right app, holds the cross-cutting rules and workflow, and points to the specific Ember skills for tokens, admin shell, shared components, page layouts, mobile and UX checks.
---

# Citadel frontend design

Entry point. Use the target app's `AGENTS.md` for routing, permissions, and API conventions. Reuse the target app's components and tokens before adding styles.

## Which skill to read

| Task | Skill |
|---|---|
| Colors, radius, type, controls, focus, theme | `ember-design-system` |
| Admin header, sidebar, panels, rows, drawers | `ember-admin-ui` |
| Existing components, composables, global classes | `ember-shared-components` |
| Ember task pages, workspaces, nav placement | `ember-page-layouts` |
| Narrow layouts, touch, keyboard, sheets, async state | global `mobile-ui` (Citadel specifics below) |
| Forms, contrast, semantics, scroll, hierarchy | global `ux-checks` |
| New page, store, API call, or route | `ember-feature-scaffold` |

## Pick the app

| Page is for | App |
|---|---|
| User-facing chat and tools | `apps/ember` |
| Staff accounts, roles, and invites | `apps/portcullis_admin` |
| Agents, gateway connections, MCP servers, and tuning | `apps/legion_admin` |
| Admin pages owned by Armory, Stronghold, or Treasury | The corresponding `apps/*_admin` app |

Use the target app's permission rules for admin routes. Portcullis enforces permissions server-side.

## Rules that cost us before

- Every panel header carries a `PanelHelp` icon first among its tools: a click opens a popover saying what the panel is for. Add it to each new panel.
- No checkboxes in admin panels, drawers or settings: an on/off or a choice from a list is a `ToggleSwitch` (a `small` one in dense lists). A checkbox is only for a form acknowledgement or checklist, such as agreeing to a policy or confirming something was read.
- Radius only via `--radius-*`, colour only via tokens. `radiusScale.test.ts` in each app fails on a literal radius.
- Scrollbar space is always reserved: every vertical scroll container (`overflow: auto`, `overflow-y: auto` or `scroll`) also sets `scrollbar-gutter: stable`, so a scrollbar that appears never pushes its content sideways. Add it in the same declaration block when writing a new scroller. Skip only small popovers and menus (`PanelHelp`, header popovers, `PopupMenu`), where a permanent gutter would look like a gap.
- Scoped CSS that a parent page also styles: use the more specific selector (`button.delete-button`).
- A switch that calls the server stays pending until the server answers; never show unconfirmed state. Browser-local settings apply instantly ("Applies instantly. Saved on this device."); settings that reach other accounts are a draft with an unsaved bar and Save.
- Destructive: red-outlined pill in a Danger zone last in the form; severe ones use `requireText`.
- Keep admin-only pages in the admin app that owns their domain.
- No reduced-motion setting, media query or test. Animations always play.
- Status needs icon + text, not colour alone.


## Workflow

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
- [ ] Nav entry follows `ember-page-layouts`
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

## Mobile specifics (Citadel)

Add these to the global `mobile-ui` skill when working in Ember or an admin app.

- Tokens come from the target app's `style.css`; keep the orange accent. Reference screens: Notes (list/editor), Brains (scoped reader), Memory (row editing), Video Downloader (jobs/results).
- Breakpoint is 767/768px. Admin panel headers wrap search and its reserved Cancel and Save slots together onto a new line. The admin shell is header-controlled (`ember-admin-ui`); record drawers are full-height on the right.
- Viewport: `apps/ember/src/App.vue` sets `--app-viewport-height` and `--app-viewport-top` from `visualViewport` (with a `100dvh` fallback). The admin shell uses `100dvh` without that bridge.
- Sheets sit above `--rail-height`, which already includes the bottom safe-area inset.
- Global coarse-pointer CSS sets button minimum height only; check width, icon buttons, segmented choices and modal close buttons for 44px.
- Reuse `BaseModal` and `ConfirmModal` for modal focus behavior.
