# capabilities/notes/

Lets agents read the notes a user chose to share. A user keeps private notes in ember (the Notes page; ember_api stores them in db_gateway) and turns on "Let agents read this note" for the ones agents may see. This capability reads only those notes, only for the asking user, and never writes. 3 tools.

## Tools

| Tool | Purpose | Connection |
|---|---|---|
| `tool_notes_listNotes` | List the shared notes (id, title, tags, date, short preview), optionally one tag. | db_gateway (HTTP) |
| `tool_notes_searchNotes` | Search the titles and text of the shared notes. | db_gateway (HTTP) |
| `tool_notes_readNote` | Read one shared note in full. | db_gateway (HTTP) |

## Slash commands

| Tool | Slash command | Parameters |
|---|---|---|
| `tool_notes_listNotes` | `/notes list` | <ul><li>`tag` - optional, default empty. Only notes with this tag.</li></ul> |
| `tool_notes_searchNotes` | `/notes search` | <ul><li>`query` - required. Text to look for, case-insensitive.</li></ul> |
| `tool_notes_readNote` | `/notes read` | <ul><li>`note_id` - required. The note's id, from the list or a search.</li></ul> |

## Typical workflow

| Sequence | Tool | Explanation |
|---|---|---|
| 1 | `tool_notes_listNotes` | See which notes the user shared, or filter by tag. |
| 2 | `tool_notes_searchNotes` | Or search for a word. |
| 3 | `tool_notes_readNote` | Read the notes that matter, by id. |

## Who can read what

- The owner comes from `identity_context.current_uid()`: ember's account uid, sent by ember_api and ai_agent, never a tool parameter. It is the same value ember_api stores as a note's `owner`.
- A note is returned only when `owner` matches and `agent_readable` is `true`. Another account's note, a note whose switch is off, a malformed id and a missing note all give the same answer ("no note with that id is available to agents").
- Without an identity, or when the server listens on a non-loopback host without `INTERNAL_API_TOKEN` (so a caller could claim any uid), every call fails and no note is read.
- Note text is returned fenced as data and capped (`services/untrusted.py`). It is the user's own writing, but it can still contain text that looks like instructions.
- What an agent reads goes to that agent's LLM provider. The switch's warning on the Notes page says so.

## Configuration

- `DB_GATEWAY_URL` (default `http://127.0.0.1:8071`), `DB_GATEWAY_INSTANCE` (default `mcp_server`) and `DB_GATEWAY_CONNECTION` (default `data`) in `.env`, read in `src/config.py`. The requests carry `INTERNAL_API_TOKEN`.
- db_gateway's `configs/config_connections.json` must list the connection under that instance, e.g. `"mcp_server": ["data"]` (the `.example` file has it). It is the same `data` connection ember_api uses, so a change in ember shows here at once.
- The record shape is ember_api's (`apps/Ember/ember_api/src/services/notes.py`): collection `notes`, fields `id`, `owner`, `title`, `body`, `tags`, `agent_readable`, `updated_at`. If that changes, change `utils/gateway.py` and `domain.py` with it.
- Starts offline. Switch it online in ember_admin (Capabilities), then each user adds it in the Supermarket.
- No state of its own: nothing is stored under `specifics/`.
