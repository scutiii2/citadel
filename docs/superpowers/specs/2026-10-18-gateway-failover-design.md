# Gateway failover for ai_agent agents - design

Date: 2026-10-18. Status: draft for implementation. Scope: `apps/ai_agent` only.

## Goal

Each agent may list backup gateways. When the gateway an agent is using runs out of tokens or credit, is rate limited, rejects its key, or is down, the agent switches to the next backup gateway and carries on, without the user seeing an error. After the failed gateway's cooldown expires, later turns use the first gateway in the list again.

## Background (current behaviour, verified in code)

- An agent is `apps/ai_agent/agents/<id>.json`, parsed by `src/agents/agent_spec.py`. `llm.gateway` names one gateway, a file `gateways/<provider>/<gateway>.json`.
- The gateway is fixed per process. `agent_spec.apply_to_environ` writes `AI_AGENT_GATEWAY` (`agent_spec.py:407`). `src/llm/anthropic_provider.py` (class `_Anthropic`) and `src/llm/openai_provider.py` read that variable through `_gateway_name()` and cache one client in `cls._client` and one in `cls._sync_client`. `DEFAULT_MODEL` and `VENDOR_LABEL` are module constants computed at import. `src/llm/model_tiers.py` reads the same variable (`own_tiers`, `clamp_default`).
- Rate limits are tracked in `src/llm/cooldown.py` as a process-wide dict keyed by provider id (`"anthropic"`). `BaseProvider.is_available()` is `has_api_key() and not cooldown.is_in_cooldown(PROVIDER_ID)`. `run_chat` and `run_interpret` catch only `RateLimitError`, start a cooldown and re-raise.
- `run_chat` is a loop of rounds. Each round streams one model call, then runs any tool calls. The tool calls of a round run only after its stream finished. So a failure raised by the stream call of a round happens before that round ran any tool.
- `ChatResult` and the usage row carry `provider_id` and `model`. The usage row's `gateway` comes from `agent_spec.effective_gateway`, the file's configured gateway, not the one actually used.

## Decisions

1. **Same provider only.** Fallbacks are other gateways of the same `llm.provider` (for example `anthropic` on `claude`, then `openrouter`, then `bedrock`). Switching provider family is out of scope: message formats differ. `laya` agents cannot have fallbacks (validation error).
2. **Config in the agent file**, inside `llm`:

   ```json
   "llm": {
     "provider": "anthropic",
     "gateway": "claude",
     "model": "claude-sonnet-5-5",
     "fallback_gateways": [
       { "gateway": "openrouter", "model": "anthropic/claude-sonnet-5.5" },
       { "gateway": "bedrock" }
     ]
   }
   ```

   `gateway` is required per entry. `model` is optional (see Model mapping). Order is priority order. Primary is first, implicitly. Unknown keys inside an entry are an error, like everywhere else in the agent file. A string entry (`"openrouter"`) is accepted as shorthand for `{ "gateway": "openrouter" }`.
3. **Automatic switching**, no admin toggle. An admin can edit the list through the existing overrides file (`.data/agent_overrides.json` holds whole agent files, so the new field works there with no extra work).
4. **Per-gateway cooldown.** Cooldown keys become `"<provider>:<gateway>"`. A cooldown on `openrouter` must not block `claude`.
5. **Pick at the start of each turn, then stay for the turn.** At turn start choose the first candidate (primary first, then fallbacks in order) that has credentials and is not cooling down. If the call fails with a failover-worthy error, put that gateway in cooldown, move to the next candidate and retry the failed round. The turn stays on the new gateway until it too fails. The next turn starts again from the top of the list, so the primary returns automatically when its cooldown ends. No flapping inside a turn.
6. **A fallback without credentials is skipped, not fatal.** The primary still fails loudly at startup as today. A fallback with a missing key, or whose gateway file does not exist, is logged once as a warning at startup and never becomes a candidate. A fallback gateway name that has no file at all is a startup error naming the agent file and field, because that is a typo.
7. **Retry only the failed round.** The round's stream call failed, so no tool of that round ran and `messages` is unchanged. Retry that same round on the next gateway. If the failed round had already streamed text to the client, emit `token_reset` first (the same event the code already emits for tool rounds).
8. **If every candidate fails or is cooling down**, behave as today: raise the last error (for a rate limit, after starting its cooldown). If all candidates are in cooldown at turn start, still try the primary and let it raise. Never loop more than once through the candidate list in one round.

## What counts as a gateway failure

New module `src/llm/gateway_failover.py` classifies an exception into a `FailureKind` or `None` (None = not a gateway problem, do not fail over, re-raise unchanged).

| Kind | Triggers | Default cooldown |
|---|---|---|
| `rate_limit` | `RateLimitError` / HTTP 429 without quota wording | Retry-After header (existing `extract_retry_after_seconds`), else 60 s |
| `quota` | HTTP 402; 429 or 400 whose message contains any of: `credit`, `quota`, `billing`, `insufficient`, `balance`, `exceeded your current` | 3600 s |
| `auth` | `AuthenticationError`, `PermissionDeniedError` (401/403) | 3600 s |
| `unavailable` | `InternalServerError` (5xx), HTTP 529 / `overloaded`, `APIConnectionError`, `APITimeoutError` | 30 s |

Not failover-worthy, re-raised unchanged: `BadRequestError` that is not quota wording (the existing `drop_rejected` handling stays), `ChatCancelled`, `TurnStopped`, the turn guard's `TimeoutError`, context-limit errors from `token_limits`, and any non-SDK exception.

Matching on message wording must be case-insensitive, must not log the message, and must live in one table in `gateway_failover.py` so a new gateway's wording is a one-line change.

Cooldown durations for `quota`, `auth` and `unavailable` come from a new section in `configs/config_tuning.json`:

```json
"gateway_failover": {
  "quota_cooldown_seconds": 3600,
  "auth_cooldown_seconds": 3600,
  "unavailable_cooldown_seconds": 30
}
```

Read through `src/core/config_files.py` `read_section`, with the defaults above when the section is absent. Document it in `configs/README.md` and add it to `configs/config_tuning.json.example`.

## Model mapping

A turn arrives with a `model` argument (a tier resolution done against the primary gateway's tier table, or the agent's pinned model). Model ids differ per gateway. For a fallback gateway, resolve the model in this order:

1. The fallback entry's own `model`, if set.
2. If the requested model is one of the primary gateway's tier ids (`llm_config.tiers(provider, primary)`), the id of the same tier in the fallback gateway's tier table (`llm_config.tiers(provider, fallback)`), if that gateway defines that tier.
3. The fallback gateway file's own default `model`.
4. `DEFAULT_MODEL_FALLBACK` of the provider class.

Put this in one function, `llm_config.model_for_gateway(provider, primary_gateway, gateway, requested_model, explicit_model)`, with unit tests for each branch. `model_tiers.own_tiers()` and `clamp_default()` keep using the primary gateway: the tiers advertised to the orchestrator do not change when a backup is in use.

## Provider changes

For both `anthropic_provider.py` and `openai_provider.py`:

- `get_client` / `get_sync_client` take an optional `gateway` argument and cache clients in dicts keyed by gateway name (`_clients`, `_sync_clients`). With no argument they use the primary, so existing call sites and tests keep working.
- `has_api_key(gateway=None)` and `is_available()` become gateway-aware. `is_available()` is true when at least one candidate has credentials and is not cooling down. The `/status` route must keep working (it calls module-level `is_available`, `has_api_key`; `agent_config.py` around line 275 builds the cooldown fields).
- Prompt caching (`prompt_cache` in the gateway file, Anthropic) is read per gateway, not once per turn: a backup that rejects `cache_control` must not get it. Recompute `use_cache`, `system` and `tools` when the gateway changes.
- Extended-thinking blocks echoed back in `messages` carry signatures that are valid only on the gateway that produced them. When switching gateway mid-turn, strip `thinking` and `redacted_thinking` blocks from earlier assistant messages before retrying. Cover this with a test.
- `run_chat`: wrap the per-round stream call in a failover loop as described in Decisions 5 to 8. Keep the existing `BadRequestError` / `drop_rejected` handling inside it.
- `run_interpret`: same candidate loop around the single non-streaming call.
- Replace the two `except RateLimitError` blocks with the classifier. Existing behaviour must stay: a rate limit with no available backup still starts a cooldown and re-raises.
- `DEFAULT_MODEL` and `VENDOR_LABEL` module constants stay as the primary's values.

The shared logic (candidate ordering, classification, cooldown start, switch bookkeeping) lives in `gateway_failover.py` as a small class, `GatewayRoute`, so the two providers do not duplicate it:

- `GatewayRoute.for_turn(provider, primary, fallbacks)` builds the ordered candidate list, skipping candidates without credentials, and picks the starting gateway.
- `route.current` is the active gateway name. `route.advance(error) -> SwitchInfo | None` classifies the error, starts the cooldown for `current`, and moves to the next usable candidate. It returns `None` when the error is not failover-worthy or no candidate is left (the caller then re-raises).
- `route.switches` is the list of `SwitchInfo(from_gateway, to_gateway, reason)` for the turn.

## Visibility

- New stream event `gateway_switch` with `from`, `to`, `reason` (`rate_limit`, `quota`, `auth`, `unavailable`), emitted with `step_event("gateway_switch", ...)` at the moment of the switch, before the retry. Never include the error text.
- `ChatResult` gets `gateway: str | None` (the gateway that produced the answer) and `gateway_switches: list[dict]` (empty by default). The usage row built in `server.py` must record the gateway actually used, not `effective_gateway`. Find where the row is built by following `agent_usage` / `usage_log` from `server.py`.
- The status payload built in `agent_config.py` gains `gateways`: for each candidate, `{gateway, available, cooldown_seconds_remaining}`. Existing keys stay.
- Phase 2 (not in this work): ember_api passing `gateway_switch` through to ember_web, an admin editor for the list in ember_admin, a chip in ember_web. Phase 1 must not break ember_api if it sees the unknown event: check how `apps/Ember/ember_api/src/services/agent_gateway.py` treats unknown event types and note the result in the final report. Do not edit ember_api.

## Out of scope

Cross-provider fallback, ember_api / ember_web / ember_admin changes, per-user gateway keys, spend-based (not error-based) switching, health-check pinging of cooling-down gateways, persisting cooldowns across restarts (the existing module-level dict resets on restart; unchanged).

## Risks

- Quota detection by message wording is gateway-specific and can drift. Mitigation: the wording table is data, unit-tested per known gateway shape, and a 402/401/403 status is matched first.
- Thinking-block signatures across gateways (see above).
- A backup gateway may serve a different model version, so answers differ mid-conversation. Accepted; the switch event and usage row make it visible.
- Tests must not call real gateways. Use fakes shaped like the SDK errors (the existing `test_anthropic_provider.py` and `test_openai_provider.py` show how the SDK is faked).

## Acceptance

1. An agent with no `fallback_gateways` behaves exactly as before (all existing tests pass unchanged).
2. With a primary that raises each failover-worthy error kind on the first stream call, the turn completes on the backup, a `gateway_switch` event is emitted, the usage row names the backup, and the primary is in cooldown for the configured time.
3. A non-failover error (plain `BadRequestError`, cancellation) is re-raised with no switch and no cooldown.
4. When every candidate fails, the last error is raised.
5. After the primary's cooldown expires, the next turn uses the primary again.
6. Invalid `fallback_gateways` (laya provider, duplicate, equals primary, unknown key, missing `gateway`, nonexistent gateway file) is rejected at startup with the file and field named.
