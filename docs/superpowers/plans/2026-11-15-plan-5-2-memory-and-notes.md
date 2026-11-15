# Plan 5.2: Memory and notes move to Stronghold

Branch: `refactor/stronghold-calendar` (same branch as 5.1; see execution notes).

## What was found first

The planned sub-plan was "notes, brains, memory". Two facts changed it:

1. Notes (tag suggestions, tag generation) and brains ask Legion agents. The agent client and directory existed only in Portcullis. Decision (2026-11-15): Stronghold gets its own copy now; Portcullis deletes its copy when chats move (5.9).
2. Brains also need usage accounting (5.6) and per-request permissions (`settings.manage`, publish). They stay in Portcullis for now and move as their own sub-plan (5.2b).

## Tasks

1. Stronghold `src/agents/`: copy of `agent_gateway.py`, `agent_directory.py`, `mcp_session.py` (traffic counting removed). Registry from `AGENTS_REGISTRY_PATH` or `AGENTS_REGISTRY_URL`.
2. Stronghold `src/memory/`: `/memory` routes, Armory client, `DELETE /memory/accounts/{uid}`.
3. Stronghold `src/notes/`: store, tag suggestions, tag writer, `/notes` routes, `DELETE /notes/accounts/{uid}`.
4. Back-channel: `POST /internal/accounts/{uid}/actions` in Portcullis; `platform.log_action` in Stronghold.
5. Portcullis: `/api/memory` and `/api/notes` pass the request on after the `chat.use` check. Account delete purges memory, calendar and notes through Stronghold. Tag services removed.
6. Brains in Portcullis read notes from Stronghold (`services/remote_notes.py`).
7. Armory's notes tools read Stronghold's database: Compose sets `DB_GATEWAY_INSTANCE=armory`, `DB_GATEWAY_CONNECTION=stronghold`; Treasury lists connection `stronghold` under that instance.
8. Account uids are kept out of request logs and traffic counters on both sides.

## Accepted behavior changes

1. Notes start empty: they are stored in Stronghold's own database. No migration, as decided. Assistant memory is unchanged; Armory still keeps it.
2. An action log line ("Created a note", "Saved a memory") is sent to Portcullis after the action. If that call fails the action still succeeds and the line is lost; a warning is written to Stronghold's log.
3. When Stronghold is down, `/api/notes` and `/api/memory` answer 502 `Stronghold is unavailable`. Before, memory answered 503 when Armory was down; that 503 still comes through when only Armory is down.
4. Armory's notes tools must point at the `stronghold` connection. In Docker, Compose sets it. For a run outside Docker, set `DB_GATEWAY_CONNECTION=stronghold` in `apps/armory/.env` and list `stronghold` under Armory's instance in Treasury's `config_connections.json`. Without this, agents no longer see shared notes.
5. A malformed note id under `/api/notes/` is refused by Portcullis with 404 and does not reach Stronghold.
6. The agent client exists twice (Portcullis and Stronghold) until chats move. A fix to one must be made in the other.
7. Traffic counters no longer count the notes and memory calls to Armory and Legion made by Stronghold; Portcullis counts one `stronghold` call instead.

## Execution notes (2026-11-15)

- Executed in full, except brains (deferred, see above). Stronghold suite: 189 passed. Portcullis: full-suite result is in the commit message.
- 5.1 and 5.2 share one branch and one commit: the calendar-only Portcullis run was interrupted twice, so one full run was made on the combined tree instead of two.
- Not run: Docker builds; Stronghold calling a real Portcullis, Armory or Legion; the Notes page in a browser; Armory reading a note written through Stronghold (both sides are covered separately by tests, the shared setting is not).
- Kept in Portcullis on purpose: `services/notes.py` (the `Note` type and `NotesService`, used by brains and their unit tests). It leaves with brains.
