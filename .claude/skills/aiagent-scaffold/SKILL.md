---
name: aiagent-scaffold
description: Add a new AI agent (a persona/specialist, a delegate-able or entry agent, a different model or gateway for an existing provider) or a brand-new LLM provider backend to the ai_agent project. Use whenever the user asks to add an AI agent, a specialist or persona for the assistant, an orchestrator, a new provider or model family (beyond Claude/OpenAI), a new gateway (OpenRouter/Bedrock/Vertex/Azure/etc), or wants another agent available for delegation in ember — even if they only describe the desired behavior ("I want an agent that specializes in X", "hook up a Gemini-backed agent") without naming ai_agent or these files explicitly.
---

# ai_agent scaffolding

Since multi-agent phase 1 (2026-10-04) **one file per agent**:
`apps/garrison/agents/<id>.json`. `python -m src.supervisor` (run from `apps/garrison/`) starts all agents:
it spawns one `python -m src.server` child per enabled file (env
`AI_AGENT_FILE`), registers it under its file-name id, prefixes its output
`[<id>] ` and restarts a crashed child with backoff. An agent file is required
to start an instance; there is no env-var-only start. Adding an agent is a
file, not code - except a new provider.

| Want | What it is | Code change? |
|---|---|---|
| A new specialist/persona, or another model/gateway on an existing provider | **Agent file** | No |
| A different agent for ember to talk to first, or one that delegates | **Entry / orchestrator** flags in the agent file | No |
| A model family that isn't Claude or OpenAI (Gemini, a native SDK) | **Provider** | Yes |

The retired pieces: roles in `prompts.json` and a hand-run
instance per `AI_AGENT_PROVIDER`/`AI_AGENT_PORT` (and the `--gateway` flag)
are not how agents are added now; every agent is an `agents/<id>.json`. Don't
hand-edit `.data/agent_registry.json` - it is the runtime registry the children
write (atomic temp file + `os.replace`); ember_api reads it.

`apps/garrison/README.md` ("Agents", "Orchestrator", "Decision layer", "Usage log") is
the source of truth this skill compresses; read it first. Running shape:
`ember_api --MCP--> ai_agent (entry) --delegate_to_agent--> specialists`, each
agent one provider+model, all `--MCP-->` mcp_server.

## Path 1 - New agent (file only)

1. Create `apps/garrison/agents/<id>.json`. The stem is the id
   (`^[a-z0-9][a-z0-9-]{0,62}$`); it is what ember_api, stored chat turns and
   the usage log name, so pick it once. Unknown keys are an error. Minimal
   specialist:

   ```json
   {
     "label": "Calculator",
     "port": 9103,
     "llm": { "provider": "anthropic", "gateway": "openrouter", "model": "claude-sonnet-5-5" },
     "persona": "You are a precise mathematician. Show every step.",
     "focus": "Arithmetic, algebra, percentages, unit conversion.",
     "tools": { "allow": ["calc_*"], "deny": [] }
   }
   ```

   Fields (full table in the README): `label`, `port` (required, unique across
   enabled files), `enabled`,
   `entry`, `llm.{provider,gateway,model,fallback_gateways,temperature,reasoning_effort,max_effort,min_tier,max_tier,max_tokens,max_tool_rounds,max_turn_tokens,max_turn_seconds}`,
   `persona`, `instructions`, `focus`, `tools.{allow,deny}` (fnmatch on tool names without the
   `main__` prefix; empty allow = all; deny wins), `orchestrator`,
   `memory_recall` (entry agent only: loads the user's newest saved notes before
   the question), `delegable` (`false` keeps the agent out of every roster; it is
   called directly, like `title-writer` and `tag-writer`) and `plan_tool`
   (`false` stops it offering `update_plan`; set it `false` on every specialist,
   the checklist is the orchestrator's). There is no `routing` block any more.
   For automatic gateway failover, set `llm.fallback_gateways` to an ordered
   list of same-provider names or `{ "gateway": "openrouter", "model": "..." }`
   objects (`model` optional; default `[]`). Keep the primary in `llm.gateway`.
   Each fallback needs a gateway file; missing files, duplicates, the primary
   name, unknown entry keys, missing/empty names, and non-list values are errors.
   Laya accepts no fallback entries. A missing primary key remains fatal;
   unkeyed fallbacks warn at startup and are skipped. Failover retries only the
   failed model round, retaining completed tools/results and stripping prior
   gateway-bound thinking/reasoning. Later turns prefer the primary again when
   its cooldown ends. See README's **Gateway failover** for model mapping,
   error kinds, cooldown tuning and stream/usage/status visibility. This needs
   no Ember changes; enable fallbacks on agent files only when asked.
2. Write `focus` as one concrete line (what it is good at, with the nouns a
   question would use). The orchestrator's roster and the optional `auto_route`
   classifier use it; a specialist without one is hard to pick. A specialist
   whose `tools.allow` names tools that are all switched off drops out of the
   roster for that turn.
3. Agent definitions in `agents/*.json` and presets in
   `gateways/<provider>/*.json` are tracked and are the shared defaults. The
   admin UI never writes them: its edits go to the untracked
   `.data/agent_overrides.json` (`{id: whole agent file}`), which shadows the
   tracked file on that machine; ember_admin's Reset to defaults drops it. Edit
   the tracked file for a change everyone should get. Keep the README field
   table in step when adding a field.
4. Restart the supervisor (`python -m src.supervisor`; it validates **every** file before starting
   anything and names the file and field on error; it also refuses a shared port
   among enabled agents or anything but exactly one `entry: true`). It watches
   `agents/` and the overrides file, so an admin edit is picked up without a
   restart.
5. Specialists never get `delegate_to_agent`. An agent with
   `"orchestrator": true` does, and sees a roster rebuilt each turn from the
   registry (so a specialist that starts or stops appears without a restart).
   Only one enabled file may set `"entry": true`; ember sends **every** turn
   there (`GET /api/agent`).
6. Name an agent for its job (`ember`, `server-ops`), never for its LLM
   (`claude-agent`).

## Path 2 - Make an agent the entry or an orchestrator

Set `"entry": true` on exactly one enabled file and `"entry": false` on the
one that had it. For delegation add `"orchestrator": true`. The roster is always
the full list of non-orchestrator agents (rebuilt each turn) and `agent_id` is an
enum of their ids; Laya shortlisting, `agent_id: "auto"` and the `routing`
block were removed (2026-10-09). Optional, off by default and configured in
`configs/config_tuning.json` under `classifier` (needs `TYPESAFE_API_KEY` or
`VERCEL_GATEWAY_API_KEY`; the text leaves the machine and is billed): `auto_route`
sends a top-level question straight to the best specialist, and `auto_tier`
picks a model tier from how hard the question looks. Specialist work streams to the caller as
`agent_start` / `agent_end` / `agent_token` plus `step_*` events stamped with
`agent_id`; a specialist's step ids can collide with the orchestrator's, so
consumers key on `(agent_id, id)` - ember_api and ember_web already do.

## Path 3 — New LLM provider backend (real code)

Use this only when the model family genuinely isn't reachable through
the existing Anthropic Messages API or OpenAI-compatible Responses API
shims — most "new" model needs are actually a new **gateway block**
under the existing `openai` or `anthropic` provider in
`gateways/<provider>/<gateway>.json` (see below), not a new provider module. Check that
first: `openrouter`, `bedrock`, `vertex`, `litellm`, `groq`,
`fireworks`, `together`, `ollama`, `vllm`, `azure`, `deepinfra`,
`perplexity` are already wired as gateways, each just a `base_url`/
`api_key` configuration in `gateways/<provider>/<gateway>.json`
under the matching provider — no new module needed for any of those.

If you do need a real new provider (a structurally different API, e.g.
Google's native SDK rather than an OpenAI-compatible endpoint):

1. Add `src/llm/<name>_provider.py`, modeled on `anthropic_provider.py`
   (the smaller of the two — `openai_provider.py`'s Responses API loop
   is more involved). It must define, at minimum:
   - A `_<Name>(BaseProvider)` class with `PROVIDER_ID`, `DEFAULT_MODEL_FALLBACK`,
     and `has_api_key()` (check whatever gateway JSON/env shape this
     provider's secrets take — see `llm_config.gateway()`).
   - Module-level `PROVIDER_ID`, `DEFAULT_MODEL`, `VENDOR_LABEL`,
     `has_api_key`, `is_available` (mirrors every existing provider
     module's tail — `agent_config.py` and `server.py`'s status route
     call these as bare module functions, not class methods).
   - `run_chat(question, history, model, enabled_extensions, request_id, depth, on_event=None, caveman=False) -> ChatResult`
     (`caveman` is the chat's terse-replies toggle; pass it to `system_prompt_for`)
     — the tool-calling loop: fetch tool schemas from `src.mcp_upstream`,
     call the model, dispatch any tool/function calls through
     `_dispatch()` (checking `delegation.TOOL_NAME` first, same as
     `anthropic_provider.py`'s `_dispatch`), loop until a final text
     answer or a round cap, checking `cancellation.is_cancelled(request_id)`
     between rounds so a mid-flight cancel actually stops it.
     Two valid shapes, both supported by `agent_config.py`'s
     `run_chat()` (it checks `inspect.iscoroutinefunction(_PROVIDER_MODULE.run_chat)`):
     - **Sync** (simplest, no live trace/token streaming): a plain
       `def`, `on_event` accepted but ignorable — dispatched via
       `anyio.to_thread.run_sync`, and any `on_event` the caller passed
       is silently dropped since a thread-offloaded sync call has no
       way to stream events back incrementally.
     - **Async with live streaming** (what `anthropic_provider.py` does —
       copy it for this shape): `async def`, set `SUPPORTS_STREAMING = True`
       at module level, and around each tool call emit
       `await on_event(step_event("step_start", id=..., tool=..., label=..., arguments=...))`
       / `step_event("step_end", id=..., ok=..., result=...)` (both from
       `src.llm.base_provider`), stream **every** round (not just the last) via the SDK's own
       streaming call, emitting `step_event("token", text=chunk)` per
       chunk; if a round turns out to contain tool calls, emit
       `step_event("token_reset")` so the client drops the text already
       shown. Run `_dispatch` via `anyio.to_thread.run_sync` (delegation
       calls `asyncio.run` and would fail inside the running loop), and
       when echoing output items back to OpenAI strip SDK-only fields
       (`parsed_arguments`) or the next request 400s. `on_event` may be
       `None` (e.g. `run_interpret`'s non-streaming callers) — guard
       every emit with `if on_event is not None:`. This is what
       ultimately reaches ember_api (and from there ember_web) as events - see
       `server.py`'s `ask()` tool (`ctx.report_progress(0, None, json.dumps(event))`)
       and `apps/Ember/ember_api/src/services/agent_gateway.py` on the other end.
   - `run_interpret(text, model) -> ChatResult` — one non-agentic
     completion, no tools offered (used to finish an AI-required
     `mcp_server` tool's result — see `server.py`'s `interpret` tool).
   - Report token spend, never enforce it: return the response's
     `total_tokens` (and `context_tokens`) on the `ChatResult`, nothing
     more. ai_agent keeps no usage store and applies no rolling
     6-hour/weekly cap — ember_api records each answer's
     `agent_usage` per account and owns the caps (chat_app, now retired,
     did the same with its `usage.db`).
     Only the per-request `max_output_tokens`/`max_context_tokens`/`max_tool_rounds` in
     `configs/config_tuning.json` live here.
     (`config_tuning.json` holds `token_limits` and `classifier` (the optional
     decision layer); `config_servers.json` holds `servers`. Both are read via
     `src/core/config_files.py`'s `read_section`. On first read, tuning
     preserves sections from the legacy `config_limits.json`; the retained
     legacy file is a backup. Laya tool shortlisting (`tool_selection`) is gone.
     Credentials live in a single `apps/garrison/.env`, seeded from `.env.example`;
     there is no `secrets/` folder.)
   - Wrap rate-limit errors into `cooldown.start_cooldown(PROVIDER_ID, seconds)`
     and re-raise, same pattern as the existing providers, so `is_available()`
     correctly reflects a provider that just got rate-limited.
2. Register it in `agent_config.py`'s `_PROVIDERS` dict:

   ```python
   from src.llm import <name>_provider
   _PROVIDERS["<provider_id>"] = <name>_provider
   ```

   This is the single point that makes `llm.provider: "<provider_id>"`
   a valid value — an id missing from this dict fails loudly at startup
   with the list of valid alternatives, by design (no silent fallback).
3. Add a tracked `gateways/<provider_id>/<default_gateway>.json` with the
   gateway block directly: `{ "label": "...",
   "api_key": "{<PROVIDER>_API_KEY}", "model": "..." }`. No wrapper keys or
   example copies are needed. Existing individual files take precedence
   over legacy combined gateway configuration during migration.
4. Add the real secret var name to `.env.example`
   (and your own gitignored `.env`) — whatever `{PLACEHOLDER}`
   you referenced in step 3.
5. Optional, per gateway: Anthropic prompt caching is opt-in with
   `"prompt_cache": true` in the gateway file (a gateway that routes to non-Claude
   models may reject `cache_control`); exact context counts come from a
   provider-side token counter handed to `src/llm/context_breakdown.py`
   (`RequestCounter`), and fall back to the estimate when absent. A new provider
   needs neither to work.
6. If the new model family's context window matters for the usage bar,
   add a substring-matched entry to `src/llm/model_limits.py`'s
   `CONTEXT_WINDOWS` (e.g. `"gemini-2": 1_000_000`) — unlisted models
   just get `DEFAULT_CONTEXT_WINDOW`, which is a safe but probably wrong
   fallback for a real provider you're adding deliberately.
7. Point an agent file at it (Path 1) with `"llm": {"provider": "<provider_id>"}`;
   the supervisor starts it with the others.

## Logging and usage

ai_agent has no logging module and no `logs/` folder, and no usage *store*.
Don't import another project's `logging_setup` (separate venvs, no shared
deps) or bolt a one-off logger onto one agent. The one durable output is the
usage log: each completed `ask` appends its `agent_usage` row (agent id and
label, provider, gateway, model, tokens, `started_at`/`finished_at`,
`delegated_by`, `request_id`, `depth`) to `.data/usage/YYYY-MM-DD.<agent id>.jsonl`
(`AI_AGENT_USAGE_DIR` overrides; a write failure warns and never fails the
turn). A new provider fills those fields from its `ChatResult`; it does not
write the file itself. The reply row (not the file) also carries `prompt`, the
`{role, content}` messages this agent received (`core/usage_log.prompt_messages`,
never the system prompt); ember_api keeps it for the admin Advanced chat-turn view.
ember_api owns usage limits and the usage reports.

## Verify before calling it done

- **Agent file**: start `python -m src.supervisor`. A bad file, a shared port or a wrong number
  of entry agents stops the supervisor with the file and field named. Then
  `[<id>]` lines appear and the agent is listed in `.data/agent_registry.json`;
  `GET /api/agent` on ember_api names the entry agent. Stop with Ctrl+C and
  confirm no child is left running and the entry leaves the registry.
- **Orchestrator**: ask the entry agent something that fits a
  specialist's `focus`; ember_web shows "Ember -> <Specialist>" while it works
  and the usage chip lists both agents. Tests: `ai_agent`
  `.venv_garrison\Scripts\python -m pytest` (the registry is isolated per
  test, keep it that way).
- **Provider**: start an agent file naming the new `provider` - a missing/bad
  API key should fail loudly at import time (`AgentConfigError`), not on the
  first request. Then run one real turn that triggers a tool call, to exercise
  the dispatch loop, and one that doesn't. If written async with `on_event`,
  drive it from ember_web's chat (not a bare script) and confirm
  `step_start`/`step_end`/`token` events arrive live - a `run_chat` that never
  calls `on_event` still returns a fine final `ChatResult`, so this only
  surfaces by watching the steps update mid-turn.
