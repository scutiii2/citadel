---
name: legion-language-provider
description: Use only when Legion needs a language provider beyond anthropic and openai (a structurally different model API), or when changing the shared run_chat/run_interpret provider loop. Most "new model" work is a gateway preset, not a provider.
---

# Legion language provider

First check whether a gateway preset is enough. `anthropic` and `openai` providers already reach OpenRouter, Bedrock, Vertex, LiteLLM, Groq, Ollama, vLLM, Azure and others as presets in `apps/legion/gateways/<provider>/<gateway>.json` (only `label`, `prompt_cache`, `model`, `models`; the connection and key live in ConversationGateway, `gateways/README.md`). Agent files: `legion-agent-scaffold`.

Providers do not talk to an SDK directly. They call the built-in ConversationGateway through a shim (`src/providers/language/anthropic_gateway_shim.py`, `openai_gateway_shim.py`, `providers/gateway_client.py`). A genuinely new protocol therefore also needs support in the gateway (see `gateway-parity`) before a provider can use it. Model the new module on `src/providers/language/anthropic_provider.py`.

## Provider module (`src/providers/language/<name>_provider.py`)

- A `_<Name>(BaseProvider)` class with `PROVIDER_ID`, `DEFAULT_MODEL_FALLBACK`, `has_api_key(gateway)` and `is_available()`, plus module-level `PROVIDER_ID`, `DEFAULT_MODEL`, `VENDOR_LABEL`, `has_api_key`, `is_available` (`agent_config.py` and `server.py` call them as bare functions).
- `async def run_chat(...)` with `SUPPORTS_STREAMING = True`: fetch tool schemas from `src/tools/mcp_client/mcp_upstream`, call the model, dispatch tool calls through `_dispatch()` (check `delegation.TOOL_NAME` first, as `anthropic_provider.py` does), loop until a final text answer or the round cap, and check `cancellation.is_cancelled(request_id)` between rounds. Copy the exact signature from `anthropic_provider.py`; it carries the chat's terse-replies flag to `system_prompt_for`.
- Live events from `src.providers.base_provider`: `step_event("step_start"|"step_end"|"token"|"token_reset", ...)`, emitted only when `on_event` is not `None`. Stream every round. Run `_dispatch` through `anyio.to_thread.run_sync` (delegation uses `asyncio.run`).
- `run_interpret(text, model)`: one tool-free completion (used for `interpret`, compaction and the router brief).
- Report token spend (`total_tokens`, `context_tokens`) on the `ChatResult`; never enforce caps. Per-request limits live in `configs/config_tuning.json` (read through `src/runtime/config_files.py`); Portcullis and Treasury own usage limits.
- Rate-limit errors: `cooldown.start_cooldown(PROVIDER_ID, seconds)` and re-raise, so `is_available()` reflects it.

## Register

1. `_PROVIDERS` in `src/agents/agent_config.py` and `PROVIDERS` in `src/agents/agent_spec.py` (and its default gateway mapping). An id missing from either fails at startup with the valid list.
2. A tracked preset `gateways/<provider_id>/<gateway>.json` (`label`, `model`, `models`). Put any real key in ConversationGateway or `.env`, never in the file; add the variable name to `.env.example`.
3. Context window: add a substring entry to `CONTEXT_WINDOWS` in `src/providers/model_limits.py`; unlisted models get 128,000.
4. Optional per gateway: Anthropic `"prompt_cache": true`; exact context counts through `RequestCounter` in `src/providers/context_breakdown.py`.
5. Point an agent file at it with `"llm": {"provider": "<provider_id>"}`.

## Verify

- Tests: `uv run pytest -q tests/test_<name>_provider.py` (model on `tests/test_anthropic_provider.py` and `test_anthropic_provider_streaming.py`) in `apps/legion`.
- A missing or bad key fails loudly at import (`AgentConfigError`), not on the first request.
- One real turn with a tool call and one without; drive the streaming one from Ember to see `step_start`/`step_end`/`token` arrive live.
