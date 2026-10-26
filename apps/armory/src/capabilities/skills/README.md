# capabilities/skills/

Reusable how-tos the assistant proposes after solving a multi-step task. Three tools (one has a slash command). A skill belongs to the account whose stable uid is in the request's identity (never a tool parameter), lives in a local SQLite file and is searched by keyword. A proposal is never returned or used until the user approves it.

## Tools

| Tool | Purpose | Connection |
|---|---|---|
| `tool_skill_search` | Search your approved skills; an empty query lists the newest | Local SQLite |
| `tool_skill_mark` | Record whether a followed skill worked (MCP-only: assistant feedback) | Local SQLite |
| `tool_skill_propose` | Propose a skill for your approval (MCP-only: written by the assistant) | Local SQLite |

## Slash commands

| Tool | Slash command | Parameters |
|---|---|---|
| `tool_skill_search` | `/skills search` | <ul><li>`query` - optional, default empty. Words describing the task; empty lists the newest approved skills.</li></ul> |

## Typical workflow

| Sequence | Tool | Explanation |
|---|---|---|
| 1 | `tool_skill_search` | Look for an approved skill before a multi-step task. |
| 2 | `tool_skill_mark` | Record whether the followed skill solved the task. |
| 3 | `tool_skill_propose` | After solving a new multi-step task, propose a skill. |
| 4 | *(manual - no tool)* | The user approves or retires proposed skills; a proposal is never used before that. |

## Rules

- No MCP tool can approve, edit or retire a skill. `utils/skill_store.set_status` is reached only from `routes.py`, which ember_api calls for the signed-in account (list, approve/retire/re-propose, edit, delete, and purge on account deletion; internal token required, `/skills/owners/{uid}/skills...`). A test pins that the tool and domain files never mention `set_status`. Until a skill is approved on Ember's Skills page it stays `proposed` and is never returned.
- Search returns only `active` skills, at most 3, ranked by FTS5. A query word of three or more characters also matches longer words that start with it.
- A skill that failed at least 3 times, and more often than it worked, is **failing** (`skill_store.is_failing`): search no longer returns it, and the Skills page shows "Often fails". Nothing retires or deletes it. The user edits it (`skill_store.update` through `PUT /skills/owners/{uid}/skills/{id}`: text changes, status stays, the worked and failed counts reset, so it is offered again) or retires it. Editing is user-side only, like approving.
- Limits: 80 / 300 / 1200 / 200 characters for title / when_to_use / steps / tools; 20 proposed and 50 active skills per account. A skill with the same title (ignoring case and spacing, unless retired) is stored once.
- The model must not put secrets or text copied from tool results into a skill. That rule is in the tool description (an instruction), not enforced by code. Search results are fenced as data (`services/untrusted.py`), which is not a security boundary.
- Keyed on the account uid. Every tool refuses when `MCP_HOST` is not loopback and `INTERNAL_API_TOKEN` is empty, and when no uid is known.
- Agents that must not write skills (`reviewer`, any agent without a tool scope) need `"tools": { "deny": ["tool_skill_*"] }` in their agent file, as for `tool_mem_*`.

## Configuration

- `MCP_SKILLS_DB_PATH` (`.env`, optional): the SQLite file. Default `specifics/skills/.data/skills.db`, gitignored.
- Toggle: the `skills` entry in `configs/config_capabilities.json`, or the Capabilities page in ember_admin. Starts offline.
