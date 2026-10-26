# Legion (Garrison v2) design

Status: implemented on `refactor/legion-v2`, including the Legion rename. Offline verification is green; Docker deployment checks are unverified because the engine is unavailable.

## Goals

1. Every agent has one **role**: `orchestrator`, `router` or `specialist`.
2. Every agent runs on one **provider kind**: `language` or `decision`.
3. Decision models (Laya, Jev) are gateways of one provider, `decision`, the same way Claude/OpenRouter are gateways of `anthropic`.
4. Fallback is the agent wrapper's job for both kinds. Providers never chain.
5. Clean `src/` layout. Rename the service to **Legion** last.

## Roles

`role` is a required field in `agents/<id>.json`. It replaces the `orchestrator` and `internal_role` definition flags. `entry` and `delegable` remain role-constrained options.

| Role | Gets | Rules |
|---|---|---|
| `orchestrator` | roster, delegation, plan tool, ask_user, memory/skill recall | may be an entry agent (`entry` stays: which orchestrator the chat opens) |
| `router` | nothing delegated, no tools | never delegable, never entry; must use a `decision` provider |
| `specialist` | its own tool scope | delegable by default; `delegable: false` stays for direct-call-only agents |

Validation rejects bad combinations (router with tools, orchestrator on a `decision` provider, specialist with a roster).
Today's files map as: `ember` = orchestrator, `router` = router, all others = specialist.

## Provider kinds

| Kind | Provider id | Gateways |
|---|---|---|
| language | `anthropic` | claude, openrouter, bedrock, vertex, … (unchanged) |
| language | `openai` | gpt, azure, groq, … (unchanged) |
| decision | `decision` | `laya`, `jev` |

Language generation and typed decisions have separate model-facing interfaces:

- `LanguageProvider.run_chat(...)`: tool loop, streaming, returns text. Unchanged behaviour.
- `DecisionGateway.ask(DecisionRequest) -> GatewayResult`: typed questions and per-question answers/confidences. `strategy.run` walks the selected arrangement. The JSON provider adapter returns the existing `ChatResult` transport shape and supplies `run_chat`/`run_interpret` entrypoints without language generation or tools.

### Decision gateways

- **`laya`**: HTTP client for the `LayaModel` service (`LAYA_SERVICE_URL`, `LAYA_TOKEN`). The service owns weights, strategies and decision rules. Legion loads nothing. The service strategy is gateway config: `strategy` in `gateways/decision/laya.json`, default `english-then-typed` (English first, typed if unsure, then narrowing and comparing). Change it there to any name from `GET /v1/strategies`; agents and callers never pick a Laya strategy. An unknown name fails at supervisor start, which checks it against the service when reachable.
- **`jev`**: TypeSafe cloud API (`POST /v1/systemone`, `TYPESAFE_API_KEY`). Stays cloud. It answers `choice`, `score` and `noul` questions: the client reduces `score` (levels) and `noul` (true/false labels) to a `choice` over those options, as today. That is a client-side reduction, not an API limit.
- Both gateways accept every question type and return `{answer, confidence}` per question.
- **Removed**: `jev_vercel`, `VERCEL_GATEWAY_API_KEY`, `laya_classifier` (local 512-window backend), `triage_flow.py` voter mixing, `classifier.chains`.

### Arrangement and strategies

The decision provider has one **arrangement**: the ordered gateway list `[laya, jev]`. An agent picks a **strategy** over it:

| Strategy | Behaviour |
|---|---|
| `laya-only` | ask `laya`; no cloud call |
| `jev-only` | ask `jev` |
| `both` | ask the first gateway in the arrangement (`laya`); ask the next (`jev`) only if the first fails or does not reach the confidence threshold |

The wrapper (not the provider) walks the arrangement, the same way language agents walk `fallback_gateways`. A gateway error, cooldown or confidence below threshold hands over to the next. The last answer is returned with an `uncertain` flag if no gateway reached the threshold. `laya-only` never leaves the machine; a request marked `local_only` forces `laya-only`.

```json
"llm": {"provider": "decision", "strategy": "both"}
```

`gateway` and `fallback_gateways` stay for language providers only. Thresholds: one `min_confidence` per agent (default 0.90, overridable per request), replacing the per-voter table.

## Target `src/` layout

```
src/
  server.py  supervisor.py
  agents/
    agent_spec.py  agent_config.py  agent_registry.py  agent_store.py
    agent_roles.py  agent_events.py  auto_tier.py  prompt_config.py
    roles/
      orchestrator/   # delegation, plan, ask_user, memory/skill recall, summarizer, auto_route
      router/         # router_contract, router_engine, router_service, router_client, router_routing
  providers/
    base_provider.py  gateway_failover.py  cooldown.py  cancellation.py
    token_limits.py  model_tiers.py  reasoning_effort.py  llm_config.py  llm_options.py
    language/
      anthropic_provider.py  openai_provider.py  openai/
    decision/
      contract.py  questions.py  settings.py  strategy.py  provider.py  laya_model.py
      gateways/       # laya.py, jev.py
  tools/
    mcp_client/  private_extensions/
  runtime/            # approvals, questions, broker, internal_auth, usage_log, tuning_overrides, config_files
```

Moves preserve existing basenames and history. Specialists use the shared agent
logic and have no separate role package. Gateway contracts and the strategy runner
answer typed requests; the decision provider adapter fits the existing agent
transport methods and reads its agent configuration at that boundary. Existing
language-provider integration with agent tools is retained.

## Config layout

- `gateways/{anthropic,openai}/*.json` retain their provider-folder layout; `gateways/decision/{laya,jev}.json` adds the decision presets. The approved plan amends the proposed language subdirectory split.
- `agents/*.json`: add `role`; the old Laya provider becomes `llm: {"provider": "decision", "strategy": "both", "min_confidence": 0.9}`; language-only gateway/model/generation fields are rejected for decision agents.
- `configs/config_tuning.json`: remove `classifier.chains`, `triage_*` voter settings; keep per-feature enable/threshold under agent files or a slimmed section.

## Outside consumers to update

`ember_api`: `services/agent_directory.py`, `services/agent_admin.py`, `routes/triage.py`, retired strategy-route removal, tuning routes, `config.py`, `configs/config_app.json*`.
`ember_admin`: `AgentsAdminClient.ts`, `AgentForm.vue`, `AgentAdminCard.vue`, `TuningAdminView.vue`, `TuningClient.ts`, `e2e/router-agent.spec.ts`.
Also `docker-compose.yml`, `apps/armory` references, docs, the vault notes `Brain/Projects/Citadel.md` and component notes, and `aiagent-scaffold` skill (both skill folders via `sync_skills.py`).

## Migration

Hard break, no compat shim. All agent files found by the migration glob (19 in this checkout) migrate in the same change set as the admin UI form, so no mixed state. Unknown keys already error loudly at supervisor start.

## Phases (green task commits within each)

1. [x] **Move**: restructure source directories without renaming basenames; imports only.
2. [x] **Role**: required roles, migrated definitions and Ember role integration.
3. [x] **Decision provider**: contract, Laya/Jev gateways and strategies; migrate callers,
   remove retired classifiers/default strategy controls; validate Laya strategy at startup.
4. [x] **Docs and skills**: current package names, provider-folder config shape, vault notes
   and scaffold instructions, synced through `sync_skills.py`.
5. [x] **Rename**: `apps/garrison` to `apps/legion`, compose, consumers, docs and vault.

## Risks and open checks

- Router and automatic-feature callers now use decision strategies. The automatic-feature runtime confidence default remains 60; the new example explicitly selects 80. Router confidence defaults to 0.9. Offline cases and router tests cover abstention, fallback and usage, without proving model accuracy.
- Jev's `score`/`noul` answers come from a choice reduction; keep that mapping tested.
- Confirm the configured Laya strategy appears in `GET /v1/strategies` of the deployed service.
- Rename touches the docker network name and port env; verify `dev_deploy.bat` and the ZimaOS overlay.

## Testing

Existing suites move with their modules. New: role validation matrix, decision-provider contract tests with fake gateways, fallback order (error, unsupported, low confidence, `local_only`), agent-file migration check over all `agents/*.json`.
