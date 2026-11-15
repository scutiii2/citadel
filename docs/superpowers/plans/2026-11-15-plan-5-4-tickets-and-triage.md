# Plan 5.4: Tickets and triage move to Stronghold

Branch: `refactor/stronghold-tickets-triage`. Triage needed usage accounting, which moved in 5.6.

## What moved

1. Stronghold `src/tickets/`: Armory ticket client, the reporter routes (`/tickets...`) and staff routes (`/ticket-admin/...`), the reporter projection (staff fields never reach reporters), and the read receipts. Armory still keeps the tickets.
2. Read receipts ("has staff activity I have not opened") are Treasury documents, collection `ticket_seen`, key `<uid>:<ticket id>`. The activity time comes from Armory on every list and read, so Stronghold no longer keeps a copy of it.
3. Stronghold `src/triage/`: the typed questions (a copy of `triage_questions.py`) and `/triage/titles`, `/triage/ask`. Stronghold checks and records token usage itself (`src/usage`), with its own copy of `usage_rows` (`src/usage/rows.py`).
4. Portcullis `/api/tickets`, `/api/admin/tickets`, `/api/admin/ticket-groups` and `/api/triage` check the login and permission and pass the request on. Ids are checked in Portcullis; everything else in Stronghold. `services/ticket_gateway.py`, `ticket_unread.py` and `triage_questions.py` removed.
5. Account delete purges the account's read receipts through Stronghold (`DELETE /tickets/accounts/{uid}`, best effort, `admin.tickets_purge`).
6. Portcullis passes Stronghold's `Retry-After` on (a triage question over a token limit still answers 429 with it).

## Accepted behavior changes

1. Every account's tickets show as unread once: read receipts start empty (no migration, as decided). Opening a ticket clears it.
2. The ticket's `verified_context.account_id` is the account's uid now (a text), not Portcullis's counting id. Armory only stores it.
3. Armory down or refusing with 5xx: `/api/tickets` answers 502 `Stronghold is unavailable` (before: `mcp_server is unreachable`). Armory's own 404 and 4xx messages still come through as 404 and 400.
4. Triage errors in the Errors log keep their sources (`triage.titles`, `triage.ask`) but no longer name the account that asked.
5. A token-limit check that cannot be answered refuses a triage question with 503 (Stronghold's own storage is the thing that is down), as for chat turns.
6. The old SQL tables `ticket_staff_activity` and `account_ticket_seen` stay in Portcullis's database, unused (migration `0018` is untouched).
7. `usage_rows` exists in Portcullis and Stronghold until chats move (5.9): change both.

## Execution notes (2026-11-15)

- Stronghold suite: 326 passed. Portcullis: full-suite result is in the commit message.
- Not run: Docker builds; Stronghold against a real Armory for tickets or a real Laya for triage; the Tickets page in a browser.
