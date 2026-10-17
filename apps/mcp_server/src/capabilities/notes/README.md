# capabilities/notes/

Lets agents use the notes a user chose to share. A user keeps private notes in ember (the Notes page; ember_api stores them in db_gateway) and turns on "Let agents read this note" for the ones agents may see. This capability reads and changes only those notes, only for the asking user. Agents can also create a new note. They can never delete a note or change its switch. 6 tools. (Memory, `/memory`, is a different store.)

## Tools

| Tool | Purpose | Connection |
|---|---|---|
| `tool_notes_listNotes` | List the shared notes (id, title, tags, date, short preview), optionally one tag. | db_gateway (HTTP) |
| `tool_notes_searchNotes` | Search the titles and text of the shared notes. | db_gateway (HTTP) |
| `tool_notes_readNote` | Read one shared note in full. | db_gateway (HTTP) |
| `tool_notes_createNote` | Create a note (shared with agents, marked as written by an agent). | db_gateway (HTTP) |
| `tool_notes_updateNote` | Replace the title, text or tags of a shared note; an empty argument keeps that part. | db_gateway (HTTP) |
| `tool_notes_appendToNote` | Add text to the end of a shared note; list items it already has are left out and counted. | db_gateway (HTTP) |

## Slash commands

| Tool | Slash command | Parameters |
|---|---|---|
| `tool_notes_listNotes` | `/notes list` | <ul><li>`tag` - optional, default empty. Only notes with this tag.</li></ul> |
| `tool_notes_searchNotes` | `/notes search` | <ul><li>`query` - required. Text to look for, case-insensitive.</li></ul> |
| `tool_notes_readNote` | `/notes read` | <ul><li>`note_id` - required. The note's id, from the list or a search.</li></ul> |
| `tool_notes_createNote` | `/notes create` | <ul><li>`title` - required. At most 200 characters.</li><li>`body` - required. At most 20,000 characters.</li><li>`tags` - optional, default empty. Comma-separated, at most 10.</li></ul> |
| `tool_notes_updateNote` | `/notes update` | <ul><li>`note_id` - required. The note's id.</li><li>`title` - optional, default empty. A new title; empty keeps the current one.</li><li>`body` - optional, default empty. The new full text; empty keeps the current text.</li><li>`tags` - optional, default empty. The new full tag list; empty keeps the current tags.</li></ul> |
| `tool_notes_appendToNote` | `/notes append` | <ul><li>`note_id` - required. The note's id.</li><li>`text` - required. Text to add after the current text. List items (`- x`, `* x`, `1. x`) already in the note are left out; other lines are always kept.</li></ul> |

## Typical workflow

| Sequence | Tool | Explanation |
|---|---|---|
| 1 | `tool_notes_listNotes` | See which notes the user shared, or filter by tag. |
| 2 | `tool_notes_searchNotes` | Or search for a word. |
| 3 | `tool_notes_readNote` | Read the notes that matter, by id. |
| 4 | `tool_notes_createNote` | Save something as a new note. |
| 5 | `tool_notes_appendToNote` | Add to a shared note without losing its text (or `tool_notes_updateNote` to rewrite it). |

## Who can read and change what

- The owner comes from `identity_context.current_uid()`: ember's account uid, sent by ember_api and ai_agent, never a tool parameter. It is the same value ember_api stores as a note's `owner`.
- A note is returned only when `owner` matches and `agent_readable` is `true`. Another account's note, a note whose switch is off, a malformed id and a missing note all give the same answer ("no note with that id is available to agents").
- Changing is limited the same way: a note can be updated or appended to only when it is the caller's own and its switch is on. Creating is limited to 200 notes per account.
- Agents cannot delete a note or change a note's switch. A note an agent creates starts with the switch on; one an agent changes gets `last_editor: "agent"` in its record. The limits (title 200, text 20,000, 10 tags of 30 characters, 200 notes) repeat ember_api's `services/notes.py`: change them together.
- Two writers at the same moment do not merge (the gateway has no compare-and-set): the last save wins.
- Writes do not always ask the user first. They ask only when the user has "Ask before tools" on.
- Without an identity, or when the server listens on a non-loopback host without `INTERNAL_API_TOKEN` (so a caller could claim any uid), every call fails and no note is read.
- Note text is returned fenced as data and capped (`services/untrusted.py`). It is the user's own writing, but it can still contain text that looks like instructions.
- What an agent reads goes to that agent's LLM provider. The switch's warning on the Notes page says so.

## Configuration

- `DB_GATEWAY_URL` (default `http://127.0.0.1:8071`), `DB_GATEWAY_INSTANCE` (default `mcp_server`) and `DB_GATEWAY_CONNECTION` (default `data`) in `.env`, read in `src/config.py`. The requests carry `INTERNAL_API_TOKEN`.
- db_gateway's `configs/config_connections.json` must list the connection under that instance, e.g. `"mcp_server": ["data"]` (the `.example` file has it). It is the same `data` connection ember_api uses, so a change in ember shows here at once.
- The record shape is ember_api's (`apps/Ember/ember_api/src/services/notes.py`): collection `notes`, fields `id`, `owner`, `title`, `body`, `tags`, `agent_readable`, `updated_at`. If that changes, change `utils/gateway.py` and `domain.py` with it.
- Starts offline. Switch it online in ember_admin (Capabilities), then each user adds it in the Supermarket.
- No state of its own: nothing is stored under `specifics/`.
