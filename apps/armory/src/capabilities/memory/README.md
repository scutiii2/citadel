# capabilities/memory/

Short notes the assistant keeps about a user between chats. Four tools (one has no slash command). Notes belong to the account whose stable uid is in the request's identity (never a tool parameter; see Rules for how far that can be trusted), live in a local SQLite file and are searched by keyword.

## Tools

Ember Web has a separate Memory page for reviewing, adding, editing and deleting
these same memories. It is distinct from the private Notes page. portcullis calls
token-protected internal HTTP routes under `/memory/owners/{uid}/notes`; only the
signed-in account's uid is used. Edits preserve creation dates, atomically update
the FTS index, and refuse stale text or a duplicate of another memory. This does
not change the four MCP tools or their ten-result search limit. The page lists
up to the full 200-memory account limit. Memory has no category or provenance fields.

| Tool | Purpose | Connection |
|---|---|---|
| `tool_mem_save` | Save one short note that outlives the chat | Local SQLite |
| `tool_mem_search` | Search your notes; an empty query lists the newest | Local SQLite |
| `tool_mem_forget` | Delete one of your notes by id | Local SQLite |
| `tool_mem_clear` | Delete all of your notes at once (MCP-only: no slash command, so it is never run by accident) | Local SQLite |

## Slash commands

| Tool | Slash command | Parameters |
|---|---|---|
| `tool_mem_save` | `/memory save` | <ul><li>`text` - required. One short fact, preference or instruction (max 500 characters).</li></ul> |
| `tool_mem_search` | `/memory search` | <ul><li>`query` - optional, default empty. Words to look for; empty lists the newest notes.</li></ul> |
| `tool_mem_forget` | `/memory forget` | <ul><li>`note_id` - required. Id of the note to delete, as shown by search.</li></ul> |

## Typical workflow

| Sequence | Tool | Explanation |
|---|---|---|
| 1 | `tool_mem_search` | Look up saved notes at the start of a conversation. |
| 2 | `tool_mem_save` | Save a fact or preference the user stated. |
| 3 | `tool_mem_forget` | Delete a note that is wrong or no longer wanted. |
| 4 | `tool_mem_clear` | Delete every note, only after the user clearly confirmed. |

## Rules

- Search matches whole words, and a query word of three or more characters also matches longer words that start with it ("movie" finds "movies"). The index does no stemming beyond that.
- 500 characters per note, 200 notes per user. An identical note (ignoring case and spacing) is stored once.
- The model may save only what the user stated, never anything from a tool result, web page, file or another agent. This rule is in the tool description (an instruction), not enforced by code.
- Search results are fenced as data (`services/untrusted.py`), but a fence is not a security boundary.
- Recall: an entry agent with `memory_recall` on in its agent file (`ember` has it) loads the newest notes automatically at the start of each top-level turn, through this capability's `tool_mem_search`. `ai_agent` relies on the first line of the answer's `message` field (`N saved note(s):`), so keep that wording and the `message` field stable (pinned by a test in `tests/test_memory_capability.py`). Other agents, and any agent whose `tools.deny` covers `tool_mem_*`, get no automatic recall and rely on the model calling `tool_mem_search`.
- Notes are only returned to their owner, and this server never forwards notes to extensions (the model can still quote a note in another tool's arguments).
- Account identity comes only from a verified Portcullis requester token. Service assertions authenticate callers; missing identity refuses account operations.
- Account identity comes only from a verified Portcullis requester token. Service assertions authenticate callers; missing identity refuses account operations.
- The number of distinct uids is not capped; only 200 notes x 500 characters per uid.

## Configuration

- `MCP_MEMORY_DB_PATH` (`.env`, optional): the SQLite file. Default `specifics/memory/.data/memory.db`, gitignored.
- Toggle: the `memory` entry in `configs/config_capabilities.json`, or the Capabilities page in ember_admin.
