# Admin page visibility: hide sidebar pages for every account

An administrator can hide pages from the ember_web sidebar for everyone. Hiding is nav-only: the button
disappears, the page still opens by its URL and its permissions are unchanged.

## Decisions

| Question | Choice |
|---|---|
| What "hide" means | Nav only. The route and permissions stay as they are. |
| Who it applies to | Every account (not per role). |
| Pages an admin cannot hide | `/` (Chat, the home page) and `/settings`, so nobody loses the way home or their preferences. |
| Games button | Always visible by default (today it is hidden until the account has a game). An admin can hide it like any page. |

## Backend (ember_api)

`app_settings` holds only booleans and ember_api does not know the page list (ember_web owns it). So the hide
list is one extra setting, `hidden_pages`, stored in `app_settings` as a JSON list. No migration: a missing row
means "nothing hidden".

- `GET /api/settings/pages` (any logged-in account) returns `{"hidden": ["/usage", "/agents"]}`.
- `PUT /api/admin/settings/pages` (`settings.manage`) takes `{"hidden": [...]}` and returns what was stored.
  Each id matches `^/[a-z0-9-]+$` (so `/` cannot be sent), at most 20 ids, de-duplicated and order kept.
  `/settings` is refused with 400 ("That page cannot be hidden").
- The change is written to the activity log as `settings.pages` with the before and after lists.
- `SettingsService` gains `hidden_pages()` and `set_hidden_pages()`. The value column is `String(200)`, so the
  stored JSON must stay under 200 characters; 20 ids of at most 32 characters are checked against that in the
  service (a longer list is a 400).

## ember_web

- New store `pageVisibility` (`hidden: string[]`, `ready`) loaded at login together with the games list and
  dropped when the account changes.
- `visiblePages(hasPermission, hidden)` drops pages whose `to` is in `hidden`, except `/` and `/settings`
  (defence in depth: even a bad list from the server cannot remove them). The `/games` special case goes away:
  Games follows the same permission rule as the others, with an empty permission.
- The nav rail, narrow-screen bar, Overview cards, account "more pages" list and each user's Sidebar editor all
  call `visiblePages`, so they stay consistent. An admin-hidden page is not offered in the user's Sidebar editor.
- Direct URL access is unchanged.

## ember_admin

Workspace settings gets a "Sidebar pages" section below the existing setting: one switch per page (Capabilities,
Agents, Games, Usage, Tickets) labelled "Show in the sidebar for everyone". Like the existing global setting,
a flip is a draft until Save; the bar says it applies to every account; Cancel drops the draft; Reset to default
shows every page. ember_admin cannot import ember_web's page list, so it keeps a small copy (`id`, `label`) with a
comment pointing at `ember_web/src/router/pages.ts`. An id it does not know is harmless: ember_web ignores
unknown ids.

## Testing

- ember_api pytest: read as any account, write needs `settings.manage`, validation (bad id, `/`, `/settings`,
  too many, too long), round trip, audit line, default is an empty list.
- ember_web Vitest: store load, reset on account change, `visiblePages` with hidden ids and the protected pages,
  nav rail and Sidebar editor hide an admin-hidden page, Games visible with no games.
- ember_admin Vitest: section lists the pages, draft then Save sends the list, Cancel and Reset behave.

## Risks

- The two page lists (ember_web, ember_admin) can drift. A new ember_web page then has no switch until the
  admin copy is updated. The comment and the plan's final check mention it.
- A hidden page is still reachable by URL; the admin text says "hide from the sidebar", not "disable".
