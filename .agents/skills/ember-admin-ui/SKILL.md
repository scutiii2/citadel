---
name: ember-admin-ui
description: Use when building or restyling a Citadel admin app page (portcullis_admin, legion_admin, armory_admin, stronghold_admin, treasury_admin): header and sidebar shell, searchable panels, record rows, draft Save/Cancel slots, or right-side record drawers.
---

# Citadel admin UI

Approved patterns for the admin apps. Tokens and radius: `ember-design-system`. Shared components: `ember-shared-components`. Mobile and UX: global `mobile-ui` and `ux-checks` (workspace skills).

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

