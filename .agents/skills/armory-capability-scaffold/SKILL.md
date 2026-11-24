---
name: armory-capability-scaffold
description: Use when adding a new Armory capability (a tool folder under apps/armory/src/capabilities) or a tool or slash command to an existing one, or reviewing whether a capability follows the contract/domain/tool split, the Capability subclass, help.json and README tables. Not for writing the tool function itself (armory-tool-conventions) or a new service (root-project-scaffold).
---

# Armory capability scaffolding

Armory is Citadel's MCP tool server. `apps/armory/src/capabilities/README.md` ("Shape of a capability", "Add a new capability") is the source of truth; this is the checklist. Read `server_manager/` end to end once: it shows every convention.

## New capability or something else?

- **New tool on an existing capability**: add the `contract.py` model, a method on its `<Name>Desk` in `domain.py`, and the `tool.py` pair. Leave `__init__.py` alone.
- **Outside MCP server**: not a capability. Armory does not proxy other MCP servers; it is a Legion connection (Legion Admin, Connections).
- **Persona, agent, or UI page**: `legion-agent-scaffold` or `ember-feature-scaffold`.
- **Data the user owns** (brain, skills, tickets): Stronghold serves these, not Armory.

## The split

| File | Holds |
|---|---|
| `contract.py` | Pydantic request/result models only. Results end with `message: str` (ember shows it first) |
| `domain.py` | Logic, typed in and out. Imports only `src/services/*`, never `mcp` or `tool.py`. One class `<Name>Desk`. No dependency per call: module ends `desk = <Name>Desk()` and the tool calls `domain.desk.op(...)`. Needs a client or root: pass it to `__init__`, built in the tool. Pure helpers stay module-level. No second public class |
| `tool.py` | Thin glue: load settings, call one Desk method, return. `@mcp.tool()` only here; also `@command(...)` (unless MCP-only) and `@offload` |

## Folder top level (closed list)

`contract.py`, `domain.py`, `tool.py`, `help.json`, `README.md`, `STATIC-GUIDELINES.md`, `__init__.py`, `utils/` (other `.py` files), `gui/` (`page.json` only, optional), `static/` (curated reference data, one subfolder per category with its own README). No runtime state or config inside: state goes to `.data/armory/<name>/`, cache to `.cache/armory/<name>/` (gitignored), tunable settings to the `tuning` table in `settings.db` (`apps/armory/docs/settings.md`). Wire paths as `Settings` fields in `src/config.py`.

## Registering

1. Folder with `__init__.py`.
2. Write the three files (tool function rules: `armory-tool-conventions`).
3. `README.md`: tables `## Tools` (`Tool | Purpose | Connection`), `## Slash commands` (`Tool | Slash command | Parameters`), `## Typical workflow` (`Sequence | Tool | Explanation`), then specific sections. Copy `server_manager/README.md`.
4. `STATIC-GUIDELINES.md` is mandatory when the capability makes any dot-folder or `static/` subfolder.
5. `help.json` (`summary`, `tools`, `commands`, `workflow`): same facts as the README tables; copy the shape from `math/help.json`. `commands[].name` is the bare sub-command (`list`, not `/server list`). A manual step uses `"(manual - no tool)"`. Keep README, `help.json` and the `@command`/`@mcp.tool` set in step.
6. `__init__.py`: subclass `Capability` (`services/capability_base.py`) with `id` (the `/<id>` slash name) and `label`, expose `CAPABILITY = MyThing()`. Optional: `process_lifetime_modules`, `install_routes(app)` (always-on routes; need a restart), `on_startup()`.
7. No `run.py` edit and no toggle entry. A new folder starts offline: refresh on Armory Admin's Capabilities page (`POST /capabilities/refresh`), then switch it online. Re-toggle to reload code; shared `src/services` modules need a restart.

## Verify

- `uv run pytest -q` on the capability's tests in `apps/armory` (Desk methods tested with fakes) plus `tests/test_tool_display_labels.py` and `tests/test_read_only_declarations.py` (a new capability goes in its `READ_ONLY` or `NEVER` map).
- Start Armory, refresh, switch online: no `load_error` in `GET /capabilities`, and `/<id> help` renders.
- Result model has `message`, and list fields have uniform keys so they render as a table in ember.
