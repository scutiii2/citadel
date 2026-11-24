---
name: armory-tool-conventions
description: Use when writing or reviewing an Armory tool function (tool.py) - naming, parameters and descriptions, display_label, caller identity, per-account data, read-only hints, ai_explain_result, MCP-only tools, command form inputs, logging.
---

# Armory tool function conventions

Layout and registering: `armory-capability-scaffold`. Copy from `server_manager/tool.py`. Reference for form hints: `apps/armory/src/capabilities/README.md` ("Form inputs", "Declaring a tool read-only").

- **Name:** `tool_<alias>_<camelTask>` (`tool_srv_listApps`); the function name is the tool name. A tool with `@command` gets `/<id> <snake_task>`. A capability with an audit trail has a tool-only `getAuditLog` (`meta={"hidden": True}`, no `@command`).
- **Parameters:** `Annotated[type, Field(description=...)]`, every one described (the schema feeds MCP clients and ember's command form). Multi-item parameters take a comma-separated string and return a result with a `failed` list.
- **Meta:** `@mcp.tool(meta={"keywords": [...], "display_label": "Checking app status"})`. `display_label` is mandatory (tested), present tense, not the tool name.
- **Keep the list short:** every schema goes to the model each turn. Merge near-duplicate tools (`tables` has one `tool_tables_rows`).
- **No AI in tools:** deterministic only. If the result needs explaining, set `"ai_explain_result": True` in meta. No `needs_ai_review`, `pending_ai_review`, `ai_instructions`, `ai_required`, and no LLM client import.
- **Caller identity:** never a tool parameter. Use `current_username()`, `current_email()`, `current_uid()` from `src/services/identity_context.py` (set from the signed requester identity). Absent gives `""`.
- **Per-account data:** owner is `current_uid()`, never the username. Refuse plainly with no identity. Another account's record, a missing one and a bad id answer the same "not available". Return stored user text fenced via `services/untrusted.py`.
- **Config knows it:** if a value comes from config, look it up in the tool, fail naming the file, and say in the docstring not to ask the user. Show it read-only with the `shows` form hint.
- **Docstring:** what it reads, what it computes deterministically, and what to run before or after in a workflow. The model reads it.
- **Read-only:** a tool that changes nothing sets `annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=...)`. Ember's Auto approval then runs it unasked, so never for writes, sends, deletes, commands, credit spend or crawling. `tests/test_read_only_declarations.py` pins the list; edit it deliberately.
- **MCP-only tools:** skip `@command` when a parameter cannot be written as `key=value` (for example `list[Model]`), or the tool is destructive in bulk. Comment why.
- **Form inputs:** control ember's command form through the parameter schema (`Literal`, `examples=`, `json_schema_extra` hints `input`, `options_url`, `depends_on`, `sets`, `shows`, `initial`). Never add per-capability branches to `ToolRunForm.vue` or `toolSchema.ts`. An options route is a small GET in `src/command_routes.py`. Keep README "Form inputs", `commands.py` `CommandParam` and the modal in step.
- **Logging:** `logger = logging.getLogger(__name__)` in `domain.py`. Never call `configure_logging()` or add a handler.
