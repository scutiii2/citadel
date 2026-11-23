# Treasury Admin redesign specification

Bring Treasury Admin to the design of the redesigned [Portcullis Admin](2026-11-23-portcullis-admin-redesign-design.md) and Legion Admin. Follow the [Citadel frontend skill](../../../.agents/skills/ember-frontend-design/SKILL.md) and its [mobile guide](../../../.agents/skills/ember-frontend-design/mobile-ui.md). Keep the three apps' shared components identical copies.

## Today

Treasury Admin still uses the old shell and patterns: a 52px icon rail (`TreasuryNav.vue`) with a cycling theme button and Log out, no header, page-level titles and descriptions, inline `card` forms below tables, a text Cancel, and no search. It has four pages (Instances, Connections, Services, Outside services), all gated by `settings.manage`. It has no e2e specs and none of `ThemeSelect`, `AdminSearch`, `RecordDrawer`, `StatusFilters`, `DraftActions` or `useDraftPanel`.

## Shell and navigation

- Replace the rail with the compact full-width header and the sidebar used by Portcullis (`PortcullisHeader`, `AdminNav`). Header left: sidebar toggle, Treasury Admin identity, divider, current page title (`pageTitle(route.path)` from `router/pages.ts`). Header right: Notifications, Help, Profile. Profile holds identity, the labeled Dark/Light/System `ThemeSelect`, and Log out. A signed-out page keeps a reachable `ThemeSelect`.
- Keep the four pages in `TREASURY_PAGES`, filtered by permission as now. The sidebar shows labels expanded and named icons collapsed. Below 768px the header toggle discloses it above the content. Keep the other admin apps as shortcuts at the bottom, from `ADMIN_APPS`, excluding Treasury.
- Notifications show only real signals Treasury Admin already has: Treasury not answering (from the Instances check). With none, show an empty state. Do not add config-issue or fake counts. Help explains the four pages and the "applies now" versus "from the next start" wording.
- Delete the hidden-title duplication: the header is the one visible title. Pages drop `description` from the body when the shell is signed in, as Portcullis does with `.portcullis-shell`, and keep task-specific section headings and notices. Keep the redirect to login on session expiry and the no-access behavior.
- Copy `ThemeSelect.vue`, `useDraftPanel.ts`, `AdminSearch.vue`, `RecordDrawer.vue`, `StatusFilters.vue`, `DraftActions.vue` and the panel geometry (`admin.css` rules from Legion/Portcullis `style.css`) without changes. Keep `useTheme` and its storage keys.

## Panels and drawers

- Every record list gets a labeled `AdminSearch` in its panel header with the single inset focus outline. Search is panel-local, hides rows only, and keeps drafts and the open drawer.
- Make each whole row open its details drawer through one native opener, with row-wide focus, table semantics kept, and independent row actions kept. Clip hover, selection and focus inside the rounded panel. Wide tables stay in a labeled local scroller (as `ServicesView` does). Return focus to the row after closing, or to search when the row is gone.
- Everything opened from a panel opens in `RecordDrawer`; only `ConfirmModal` stays modal. Edit, Expand and Close sit together in the drawer header. Expand to about 90% of the viewport, full viewport on phones. Put Cancel and Save in the persistent footer, validate before the save confirmation, and confirm discard on Cancel, Close, Escape or backdrop. Failed saves keep the input.
- Inline settings drafts use `DraftActions` immediately left of search: reserved Cancel × and Save slots, shown only while dirty, discard confirmed, focus returned to search.

## Pages

- **Connections.** One roster panel: name, type, where, used by, source tag. Search name, type, where and instance names. Replace the inline Add/Edit `card` with a create drawer and an edit drawer on `RecordDrawer`, keeping the same fields per type (SQLite file; Postgres address and pool size; Firestore project, credentials file, database), raw-SQL checkbox, per-connection cache, `formError`, and the "applies now / next start" notice. Remove and "Use the built-in" stay a `ConfirmModal` and sit last in the drawer's Danger zone. Move the cache defaults to their own searchable panel using `DraftActions` (Save and Cancel ×, "Use the built-in defaults" kept beside it) with the unsaved-changes check that `cacheChanged` does today.
- **Instances.** A read-only roster panel with Refresh in the toolbar. Search instance name and connection names. Each row opens a details drawer (connections, the Portcullis data note). "Treasury does not answer" stays a distinct error from an empty list, and also feeds Notifications.
- **Services.** One roster panel, search by name and address. Move the per-row pin form into the details drawer with Edit: staged address, Pin and "Use the registered address" in the footer after confirmation. Keep the Pinned/Registered/Default source labels, the pending state while Treasury has not answered, and no unconfirmed address shown.
- **Outside services.** One roster panel of groups, search group name, origin and service id. Rename and origin removal move into the group's drawer with the existing draft keeping behavior in `applyView`, the "Name saved. Could not refresh" partial-failure message, and the typed or plain `ConfirmModal` that exists now. A failed rename keeps its draft and shows its error inside the drawer.
- Loading, load-error, empty and no-match states stay distinct. Pending requests stay inside the owning panel.

## Carried over from the Portcullis and Legion work

These decisions were made after the first Portcullis spec and apply to Treasury too.

- **Overview page.** Add `/overview` as the first page and the landing page, as Legion Admin has. Stat tiles with an icon, a count and a footer link (Instances, Connections, Services, Outside services), a warning banner when Treasury does not answer, and a panel of page shortcuts with live details. A count that could not load is shown as Unavailable, never zero. Pages take a permission or a list of permissions.
- **Icon actions in panel headers.** Every action button in a panel header is an icon button (`admin-icon`, filled `accent` for the primary one) with an accessible name and a tooltip: Add connection (plus), Refresh on Instances (refresh icon, replaces the text Refresh), edit and pin actions inside drawers stay in the drawer footer.
- **Helper icon.** Every panel header starts its tools with `PanelHelp`, a popover saying what the panel is for. Static explanatory paragraphs move into it: the page descriptions, "applies now or from the next start" wording, the SQLite, Postgres and Firestore field hints that are not per-field help.
- **No checkboxes.** "Allow raw SQL on this connection" becomes a `ToggleSwitch`. A checkbox is only for acknowledgements and checklists.
- **Primary buttons** are rounded rectangles (`--radius-md`) with no underline when a link is styled as one. Secondary chips stay pills.
- **Status filters** do not wrap: one row, scrolling sideways when narrow. Use `StatusFilters` for the source of a connection (All, Built-in, Saved, Changed) and of a service address (All, Pinned, Registered, Default).
- **Notifications and profile menu.** The header Notifications popover is a list of rows with an icon, a title, a note and a chevron, a count badge and an empty state, fed only by the Treasury-not-answering signal. The Profile menu has identity, Profile-free links (Treasury has no Profile or Settings page, so only theme and Log out), and no Ember link.
- **Config issues, Settings and Profile** do not exist in Treasury Admin and are not added.

## Tests

- Add component tests for `AdminNav`, `TreasuryHeader`, `RecordDrawer` copy parity, and each changed panel: search with a kept draft, the row opener, discard without a write, a failed save keeping the draft, and a guarded route change. Update the four `*View.test.ts` files to the new markup. Keep `radiusScale.test.ts`, `guard.test.ts` and `index.test.ts`.
- Add `e2e/` Playwright specs on the Portcullis pattern: built app, fake API through `page.route`, one spec for the shell (sidebar at 1280, 768 and 375, Profile theme persisted), one for the four pages at desktop, tablet and mobile in both themes (no horizontal page scroll, no unexpected request), one for the drawer (expand, restore, own-body scroll, footer reachable, discard).
- Update `apps/treasury_admin/AGENTS.md` and the shared-component lists in `AGENTS.md` and the frontend skill.

## Acceptance

- All four pages render real data with one page title. Keyboard, mouse and touch can navigate, search, open rows, resize drawers, confirm or discard and return focus.
- Parity with Portcullis and Legion at desktop, 768px, 767px and 375px in Light and Dark for the shell, last-row hover and focus, search and drawers.
- Shared component copies match the Portcullis versions except for app-specific names. Radius and color use tokens only. No reduced-motion code.
- No change to API clients, permissions, storage keys, schema, runtime dependencies or deployment. New route: `/overview`. The only added package is `@playwright/test` as a dev dependency for the e2e specs, as in Portcullis Admin. The `@vitejs/plugin-vue` pin stays.
