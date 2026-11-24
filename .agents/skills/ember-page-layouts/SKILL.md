---
name: ember-page-layouts
description: Use when laying out an Ember task page (notes, memory, skills, reader, downloader), choosing list/editor or two-pane workspaces, mobile modes, or deciding where a page goes in the nav rail versus the account menu.
---

# Ember page layouts and navigation

Components come from `ember-shared-components`; tokens from `ember-design-system`; narrow screens from the global `mobile-ui`.

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

| Task | Reference under `apps/ember/src/` |
|---|---|
| Writing with secondary tools | `features/notes/NotesView.vue`: draft-safe sidebar search, growing document editor, individual tool disclosures and persistent Save |
| Reviewing proposed how-tos | `features/skills/SkillsView.vue`: grouped list/editor workspace, approval inside the selected row, document fields, visible pane scrollbars |
| Reading shared documents | `features/global/GlobalView.vue`: reader with review queue, drawers for files and skills |
| Downloading and collecting media | `features/mediaDownloader/MediaDownloaderView.vue`, `features/mediaDownloader/components/`: single-link flow, ZIP groups, temporary files |

## Navigation placement

- **Ember rail** (`NavRail.vue`): header = Overview (wordmark) + Chat. Main list = only pages backed by a dedicated Armory capability (Notes, Memory, Generator, Tickets). Every other page (Capabilities, Agents, Usage, Settings, Profile) goes in `AccountMenu.vue`.
- **Admin navigation:** use the target app's page registry, permission filtering, and navigation preferences where supported. Use the approved admin shell as the design reference.
- On existing shells with a mobile bottom rail, use `bottom: var(--rail-height)` for sheets above that rail.

