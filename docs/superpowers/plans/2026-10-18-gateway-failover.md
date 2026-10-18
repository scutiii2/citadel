# Gateway failover - implementation plan

Spec: `docs/superpowers/specs/2026-10-18-gateway-failover-design.md`. Read it first; this plan only orders the work.

All work is in `apps/ai_agent`. Tests run from `apps/ai_agent` with `.venv_ai_agent\Scripts\python -m pytest <path> -q`. Work test-first: write the failing test, run it and see it fail, implement, run it and see it pass, commit. One commit per task, only the paths the task names. Before writing any new reusable function or class, check `catalog_service` for an existing tagged building block (skill `checking-the-catalog`), and tag new reusable pieces with `@catalog` as `cooldown.py` does.

The plan names files and interfaces, not full code. Read each file before editing it and match its style. Where the plan and the code disagree, fix minimally and report the deviation.

## Task 1 - Agent file schema: `llm.fallback_gateways`

Files: `src/agents/agent_spec.py`, `tests/test_agent_spec.py`.

- Add `GatewayChoice(gateway: str, model: str | None = None)` frozen dataclass and `LlmSpec.fallback_gateways: tuple[GatewayChoice, ...] = ()`.
- Add `"fallback_gateways"` to `_LLM_KEYS`. Parse in the function that builds `LlmSpec` (near `agent_spec.py:304`) using the file's `check` helpers so errors name the file and field (`llm.fallback_gateways[1].gateway`).
- Accept a string entry as shorthand. Reject: non-list, unknown entry key, missing/empty `gateway`, duplicate gateway, gateway equal to the primary (resolved with `_DEFAULT_GATEWAY` when the file names none), and any entry when `provider == "laya"`.
- Tests: valid object form, string form, each rejection, default (empty tuple), and that the existing `apply_to_environ` is unchanged.

Commit: `feat(ai_agent): fallback_gateways in agent file schema`.

## Task 2 - Per-gateway cooldown keys

Files: `src/llm/cooldown.py`, `tests/` (find the existing cooldown tests; add to them or create `tests/test_cooldown.py`).

- Add `gateway_key(provider_id, gateway) -> str` returning `"<provider>:<gateway>"`. The existing functions already take a string key, so no signature changes; add tests that `anthropic:openrouter` in cooldown leaves `anthropic:claude` available and that `reset()` clears all.
- Keep `start_cooldown(provider_id, ...)` working for plain provider ids (existing callers and tests).

Commit: `feat(ai_agent): gateway-scoped cooldown keys`.

## Task 3 - Failure classifier and route

Files: new `src/llm/gateway_failover.py`, new `tests/test_gateway_failover.py`, `src/core/config_files.py` only if a section reader is missing (it is not expected to be).

- `FailureKind` enum: `rate_limit`, `quota`, `auth`, `unavailable`.
- `classify(error) -> FailureKind | None` per the spec table. Import the SDK exception classes from both `anthropic` and `openai` (both have `RateLimitError`, `AuthenticationError`, `PermissionDeniedError`, `InternalServerError`, `APIConnectionError`, `APITimeoutError`, `BadRequestError`, `APIStatusError`). Use `status_code` first, then the wording table (one module-level tuple of lowercase substrings). Never log or store the message.
- `cooldown_seconds(kind, error) -> float`: Retry-After for `rate_limit` (reuse `cooldown.extract_retry_after_seconds`), else the `gateway_failover` section of `configs/config_tuning.json` read through `read_section`, with the spec defaults when absent.
- `SwitchInfo` dataclass, and `GatewayRoute` with `for_turn`, `current`, `advance(error)`, `switches`, as specified. `for_turn` takes the provider id, primary gateway, fallback names and a `has_credentials(gateway) -> bool` callable (so the class has no SDK dependency and is trivially testable). `advance` starts the cooldown (Task 2 key) for the failing gateway and returns the next usable candidate, skipping ones in cooldown or without credentials. It must never return a gateway already tried in this turn.
- Tests: one per error kind and status code, wording match on 400 and 429, non-failover errors return None, ordering and skipping in `for_turn`, all-cooling-down falls back to the primary, `advance` exhausts to None, cooldown durations from config and defaults.
- Add the `gateway_failover` section to `configs/config_tuning.json.example` and document it in `configs/README.md`.

Commit: `feat(ai_agent): gateway failure classifier and route`.

## Task 4 - Model mapping

Files: `src/llm/llm_config.py`, `tests/test_llm_config.py`.

- Add `model_for_gateway(provider, primary_gateway, gateway, requested_model, explicit_model)` implementing the four-step order in the spec's Model mapping section. Reuse `tiers()` and `gateway()`; do not duplicate their parsing.
- Tests: one per branch, including a requested model that is not a tier id, and a gateway whose tier table lacks the requested tier.

Commit: `feat(ai_agent): map the requested model onto a fallback gateway`.

## Task 5 - Anthropic provider: per-gateway clients and failover

Files: `src/llm/anthropic_provider.py`, `tests/test_anthropic_provider.py`, `tests/test_anthropic_provider_prompt_cache.py` (extend, do not weaken), new `tests/test_anthropic_gateway_failover.py`.

- Convert `_client` and `_sync_client` to dicts keyed by gateway; `get_client(gateway=None)` and `get_sync_client(gateway=None)` default to the primary. `has_api_key(gateway=None)`. Make `is_available()` true when any candidate is usable. Keep module-level aliases (`_get_client`, `_get_sync_client`, `has_api_key`, `is_available`) so `agent_config.py` and tests still work.
- Read the agent's `fallback_gateways` through `agent_spec.current()`.
- In `run_chat`: build `route = GatewayRoute.for_turn(...)` at the top. Replace the single `client`, `model_name`, `use_cache`, `system`, `tools` with values recomputed whenever `route.current` changes (small local helper). Wrap the stream call so a failover-worthy error calls `route.advance(error)`; if it returns a switch, emit `gateway_switch` (and `token_reset` if text was already streamed), strip thinking blocks from earlier assistant messages in `messages`, reset `text_parts`, and retry the round. If `advance` returns None, re-raise. Keep the `BadRequestError`/`drop_rejected` path ahead of the classifier so a plain rejected option is still retried on the same gateway.
- The existing `except RateLimitError` blocks (in `run_chat` and `run_interpret`) go away in favour of the route; a rate limit with no backup must still start the cooldown and re-raise.
- `ChatResult(gateway=route.current, gateway_switches=[...])` on every return path, including the stop-message path. Add the two fields to `ChatResult` in `src/llm/base_provider.py` with defaults (`None`, empty list) so other providers are unaffected.
- `run_interpret`: same loop, non-streaming, no events.
- The breakdown lambda (`_AnthropicRequestCounter(client, model_name)`) must use the active client and model.
- Tests (fake SDK, as the neighbouring tests do): each failure kind switches and completes on the backup; the event is emitted; stripped thinking blocks; non-failover error re-raises with no cooldown; all candidates failing raises the last error; no fallbacks configured behaves exactly as before; prompt cache is applied per gateway (`prompt_cache` true on primary, false on backup).

Commit: `feat(ai_agent): gateway failover in the Anthropic provider`.

## Task 6 - OpenAI provider

Files: `src/llm/openai_provider.py`, `tests/test_openai_provider.py` (extend), new `tests/test_openai_gateway_failover.py`.

Same changes as Task 5 for the OpenAI-compatible provider (`GATEWAY_ENV`, clients at `openai_provider.py:99` and `:134`, the Responses loop near line 325, `run_interpret` near line 500). Reuse `GatewayRoute`; do not copy logic from Task 5. Mind its own message-echo rule (SDK-only fields such as `parsed_arguments` are stripped before the next request) and that reasoning items have the same cross-gateway validity problem as thinking blocks: strip them on a switch.

Commit: `feat(ai_agent): gateway failover in the OpenAI provider`.

## Task 7 - Usage row, status payload, wiring

Files: `src/server.py`, `src/agents/agent_config.py`, `src/core/usage_log.py` (only if the row builder lives there), their tests (`tests/test_usage_log.py`, plus the status route test if one exists; otherwise add one next to the closest server test).

- Usage row `gateway` = `result.gateway or spec.effective_gateway`. Add `gateway_switches` to the row only when non-empty.
- Status payload: add `gateways: [{gateway, available, cooldown_seconds_remaining}]` for every candidate; keep every existing key.
- Startup validation in `agent_config.py`: each fallback gateway must have a file (`llm_config.gateway(provider, name)` raising `KeyError` becomes an `AgentConfigError` naming the agent file and `llm.fallback_gateways`); a fallback with missing credentials logs one warning and is excluded from the candidates.
- Check how `apps/Ember/ember_api/src/services/agent_gateway.py` handles an unknown event type (read only; do not edit). Report the finding.

Commit: `feat(ai_agent): report the gateway actually used, per-gateway status`.

## Task 8 - Docs and skill

Files: `apps/ai_agent/README.md` (Agents field table and a short "Gateway failover" subsection), `apps/ai_agent/configs/README.md`, `.agents/skills/aiagent-scaffold/SKILL.md` (field list and a short Path 1 note), then run `python sync_skills.py` from the repo root (project root `MCPServer`) so `.claude/skills/` matches; `python sync_skills.py --check` must report no drift. Never edit `.claude/skills/` by hand. Do not touch `Brain/`.

Commit: `docs(ai_agent): document gateway failover`.

## Task 9 - Example agent and final checks

- Do not edit a tracked agent file to enable fallbacks (the user decides which agents get which gateways). Add the commented example to the README only.
- Run the whole `apps/ai_agent` suite: `.venv_ai_agent\Scripts\python -m pytest -q`. Fix regressions you caused.
- Manual smoke (skip if it needs real keys, and say so): start `run.bat`, confirm the supervisor still validates every agent file and `[<id>]` lines appear.

No commit unless a fix was needed.
