# Context breakdown for delegated agents

Brief for Codex. Read `AGENTS.md` first and follow it. Do not commit unless asked.

## Goal

The context panel (opened from the chat header's context meter) breaks the answering agent's prompt into system prompt, delegable agents, built-in tools, MCP tools and messages. When the orchestrator delegates, each specialist runs its own prompt and none of it is broken down. Give every agent that ran in an answer its own breakdown, shown in the panel as a per-agent section.

What the panel shows is "what each agent's prompt cost", not "how full is my context". A specialist's prompt never fills the orchestrator's window. Label the section so it does not read as a fill meter.

## What exists today

- `apps/ai_agent/src/llm/context_breakdown.py` builds the breakdown (`build_breakdown`, `breakdown_fields`). Providers (`anthropic_provider.py`, `openai_provider.py`) put `context_breakdown` and `context_breakdown_exact` on `ChatResult` (`base_provider.py`).
- `apps/ai_agent/src/server.py` (~line 261) returns those two fields for the answering agent only.
- The per-agent usage row (`apps/ai_agent/src/core/usage_log.py`, built in `server.py` ~line 257) carries no breakdown. Delegated rows reach the orchestrator through `delegation.py` (`usage_sink.extend(result.get("agent_usage"))`).
- Exact counting is a per-turn user setting, "Context accuracy" (Estimate or Exact), in ember_web (`stores/chat.ts` `contextAccuracy`, `utils/contextAccuracy.ts`, `views/SettingsView.vue`). When Exact and the context panel is on, the web sends `exact_context: true`; ember_api passes it to `ai_agent` (`routes/chats.py`, `services/turns.py`, `services/agent_gateway.py`), which binds it with `context_breakdown.bind_exact` in `agents/agent_config.py`.
- Exact counting is a contextvar. Delegates are separate MCP servers called by URL through `_call_tool(url, "ask", arguments)` in `agents/delegation.py`, so the contextvar does not reach them and `exact_context` is never forwarded.

## Changes

### 1. ai_agent

- Add `context_breakdown` and `context_breakdown_exact` to the agent's own usage row, so each agent's row carries its own breakdown. Keep the top-level fields on the response for the answering agent (the panel still reads them).
- Forward the turn's exact setting to delegates: in `delegation.py`, add `exact_context` to the `ask` arguments when `context_breakdown.exact_requested()` is true. A delegate that does not know the argument must keep working (see how `agent_gateway.py` checks `status.get("exact_context")` before sending; do the same, or confirm that old peers ignore it).
- One setting governs all agents. Exact applies to every agent in the turn, or none. Do not add a per-agent switch.
- The setting stays user-side only: the per-user "Context accuracy" preference in ember_web, sent per turn as `exact_context`. Exact costs each user tokens, so each user decides. Do not add a server-side config key, default or override in `ai_agent` or `ember_api`; when the web sends no `exact_context`, every agent estimates.

### 2. ember_api

- Add optional `context_breakdown` and `context_breakdown_exact` to `AgentUsageIn` in `routes/chats.py`. Reuse `ContextPartIn` and `MAX_CONTEXT_PARTS`. Persist and return them with the message's `agent_usage`.
- Check `services/chat_service.py` and `services/turns.py` pass the fields through. Check the per-message size caps still hold with up to 20 agent rows (see `test_chats.py` around the `agent_usage` row-limit tests).
- Tests in `apps/Ember/ember_api/tests/`.

### 3. ember_web

- Extend the `AgentUsage` type in `src/api/types.ts`.
- `ContextPanel.vue`: add a per-agent section listing each agent's parts. Show whether each is exact or estimated. Keep the existing answering-agent view unchanged.
- Tests beside the component (`ContextPanel`, `UsageChip` and chat store tests as needed).
- Follow the `ember-design-system` skill and the UI conventions the panel already uses. No reduced-motion code, see `AGENTS.md`.

### 4. Token-cost note

`apps/Ember/ember_web/src/utils/tokenCosts.ts`, entry `contextAccuracy`, says Exact costs "about 5 extra count requests ... when the prompt, tools or model change, none otherwise". That is now per agent. Rewrite it to say Exact applies to every agent that runs in an answer, so a delegated answer makes about 5 count requests per agent whose prompt, tools or model changed (cached after that), no model output. Estimate costs no tokens. Update the `contextPanel` note only if it contradicts this. Show the same note beside the setting in `SettingsView.vue` (it already uses `:cost="TOKEN_COSTS.contextAccuracy"`); check the label text says "all agents".

## Done when

- A delegated answer's panel lists one section per agent that ran, each with its own parts.
- With Exact on, delegates count exactly (or fall back to estimate, `context_breakdown_exact: false`); with Estimate, no count requests are made.
- Counting failure or timeout never fails a turn (existing behavior, keep it).
- Tests added in ai_agent, ember_api and ember_web, and the existing suites for those apps pass. Use each app's own test setup.
- The cost note is updated as above.

## Out of scope

Per-agent exact/estimate switches, a fill meter per agent, changes to how `context_tokens` is reported by providers.
