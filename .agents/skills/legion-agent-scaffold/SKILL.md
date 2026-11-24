---
name: legion-agent-scaffold
description: Use when adding or changing a Legion agent (specialist, orchestrator, router, architect, decision agent), its model or gateway preset, fallback gateways, tool allow list, or making an agent available for Ember delegation. For a new model provider use legion-language-provider.
---

# Legion agent scaffolding

An agent is one file, `apps/legion/agents/<id>.json`. Adding one is a file, not code. Sources of truth: `apps/legion/agents/README.md`, `apps/legion/README.md` ("Agents" field table, "Orchestrator", "Decision question agents", "Gateway failover"), `apps/legion/gateways/README.md`. Read the field table there; this skill does not repeat it.

| Want | Do | Code? |
|---|---|---|
| New specialist, or another model/gateway on `anthropic` or `openai` | Agent file | No |
| Different entry agent, or one that delegates | `role: orchestrator` + `entry` in the file | No |
| Typed question agent (choice, score, noul) | Agent file with provider `decision` | No |
| Model family on neither protocol | `legion-language-provider` | Yes |

Do not hand-edit `.data/agent_registry.json` or `.data/agent_definitions.json` (runtime state).

## New agent

1. Create `agents/<id>.json`. The stem is the id (`^[a-z0-9][a-z0-9-]{0,62}$`), used by Portcullis, stored turns and the usage log, so choose it once. Name it for its job (`server-ops`), never its model. Unknown keys are an error. Copy a close sibling (`mathematician.json` for a specialist) and set a unique `port` (next free from 29603 up; Ember is 29603), `role`, `llm`, `persona`, `focus`, `tools`.
2. `focus`: one concrete line with the nouns a question would use. The orchestrator roster and `auto_route` read it. A specialist whose allowed tools are all switched off drops out of the roster for that turn.
3. `tools.allow` and `deny` are fnmatch globs (deny wins). Armory tools are named `tool_<alias>_...`; Stronghold tools `stronghold__tool_...`; an outside MCP connection's `<server-id>__<tool>` needs an explicit allow glob. A specialist that may file tickets needs `stronghold__tool_ticket_createTicket`.
4. Set `plan_tool: false` on specialists (the checklist is the orchestrator's). `delegable: false` keeps a helper out of every roster (called directly, like `title-writer`, `tag-writer`, `context-summarizer`).
5. Fallback gateways: `llm.fallback_gateways` (same-provider names or `{gateway, model}`), only when asked. Each needs a preset file. See README "Gateway failover".
6. Tracked `agents/` and `gateways/` files are shared defaults. The admin UI never writes them: edits go to the `agent_overrides` table of `.data/settings.db`, which shadows the tracked file on that machine. Edit the tracked file for a change everyone gets. Add a new field to the README table.

## Roster rules

The enabled agents must hold exactly one orchestrator (the one with `entry: true`), exactly one router, at least one architect and at least one specialist. Enabled ports are unique. Only a language-provider orchestrator may be entry or receive roster and delegation tools; specialists never get `delegate_to_agent`. Routers have no tools and use provider `decision`. Architects need `kind`, `workers`, `tools.deny: ["*"]`. Specialist work streams as `agent_start`/`agent_end`/`agent_token` and `step_*` events stamped with `agent_id`; consumers key on `(agent_id, id)`.

## Decision agents

Provider `decision`: `llm.strategy` (`laya-only`, `jev-only`, `both`) and optional `llm.min_confidence` (above 0, at most 1). Gateway, model, generation and fallback fields are rejected. Laya's internal strategy is `gateways/decision/laya.json`, read on every call. Automatic tier and specialist routing use `classifier.auto_tier` and `classifier.auto_route` in `configs/config_tuning.json`.

## Usage log

Each completed `ask` appends its `agent_usage` row to `.data/usage/YYYY-MM-DD.<agent id>.jsonl` (`AI_AGENT_USAGE_DIR` overrides; a failed write warns and never fails the turn). A provider fills fields from its `ChatResult` and never writes the file. Portcullis and Treasury own limits and reports.

## Verify

- Run `python -m src.supervisor` from `apps/legion` (or `uv run pytest -q tests/test_agent_spec.py tests/test_agent_files.py`). A bad file, shared port or wrong roster stops it naming file and field.
- `[<id>]` lines appear, the agent is in `.data/agent_registry.json`, and `GET /api/agent` on Portcullis names the entry agent.
- Orchestrator: ask something that fits a specialist's `focus`; Ember shows the handoff.
