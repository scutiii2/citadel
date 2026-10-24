# Brief: improve the user tickets page in ember_web

Handoff for Codex. Delete this file when the work is merged.

## Context

`ember_web` already has a user tickets page:

- View: `apps/Ember/ember_web/src/features/tickets/TicketsView.vue` (list, status filter, new-ticket modal, detail modal with comment thread, reply, close with confirm)
- Client: `apps/Ember/ember_web/src/features/tickets/api/TicketsClient.ts` (`list`, `get`, `create`, `comment`, `close`)
- Helpers: `apps/Ember/ember_web/src/features/tickets/utils/tickets.ts`
- Backend: `apps/Ember/ember_api/src/routes/tickets.py`, `src/services/ticket_gateway.py`
- Admin side (do not break): `apps/Ember/ember_admin` tickets kanban

The `Ticket` type is reporter-only: ember_api never sends tags, priority or other people's data to this page. Keep it that way.

Follow `AGENTS.md`, the `ember-feature-scaffold` and `ember-design-system` skills in `.agents/skills/`, and the radius and token conventions already used in `TicketsView.vue`. No reduced-motion code (see `AGENTS.md`). Use the Ember accent token, not a hardcoded orange.

## Scope: phase 1 (do in this order, one commit each)

1. **Unread signal.**
   - Backend: track the last staff activity per ticket and a per-user `last_seen_at` per ticket. Add an Alembic migration (next number after the latest in `apps/Ember/ember_api/migrations/versions/`).
   - Expose `has_unread` on each ticket in `GET /api/tickets`. Opening a ticket (`GET /api/tickets/{id}`) marks it seen.
   - Add `GET /api/tickets/unread-count` or include a count in the list response, for the nav badge.
   - UI: orange dot and border on unread rows, "Support replied" label, count badge on the Tickets nav entry.
2. **Duplicate feedback on create.** `create` already returns `duplicate` and `group_size`. Use them: when `group_size > 1`, show "Ticket #N filed. X other people reported something similar, so yours is grouped with them." Otherwise keep the current notice.
3. **Reopen.**
   - `POST /api/tickets/{id}/reopen`, allowed for the reporter on `resolved` and `closed` tickets, sets status back to `open`, adds a system comment.
   - UI: the footer "Close ticket" button becomes "Reopen ticket" when status is `resolved` or `closed`. No confirm modal needed.
4. **Deep link.** Route `/tickets/:id` opens the detail modal directly. Closing the modal goes back to `/tickets`. Unknown or foreign id shows the existing error state, not a crash.

## Scope: phase 2 (only if phase 1 is clean)

- Status counts on the filter chips (from one list call, not one per status).
- Title search and sort by `updated_at`.
- Status timeline (Open, In progress, Resolved) at the top of the detail view, using `closed_at` and `created_at`.
- Character counters on title (120) and description (4000).
- Poll the list every 30 s while the page is visible. Stop when hidden.

## Out of scope

Attachments. Split-pane layout. Anything in `ember_admin`.

## Design reference

Layout: header with title and "New ticket" button, status chips with counts, search box, rows with dot, title, type pill, status, id and updated time. Detail: title, type pill, filed time, timeline, description, thread (staff left, user indented right), reply box, Close or Reopen on the left, Send on the right.

## Done means

- Backend tests in `apps/Ember/ember_api/tests/test_tickets.py` cover unread, reopen and ownership (a user cannot see or reopen another user's ticket).
- Migration test (`tests/test_migrations.py`) passes.
- Frontend tests updated in `TicketsView.test.ts` and `TicketsClient.test.ts`.
- `npm run test` / type check in `ember_web` and `pytest` in `ember_api` pass.
- Update `README.md` for ember_web and ember_api, and the vault note `Brain/Projects/ember_api.md` if routes change.
- Do not touch the unrelated uncommitted changes in the working tree (ascension removal, admin router). Work on a new branch.
