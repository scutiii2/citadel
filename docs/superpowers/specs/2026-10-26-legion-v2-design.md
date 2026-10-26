# Legion (Garrison v2) design

Status: draft for review. Replaces `apps/garrison` with `apps/legion`.

## Goals

1. Every agent has one **role**: `orchestrator`, `router` or `specialist`.
2. Every agent runs on one **provider kind**: `language` or `decision`.
3. Decision models (Laya, Jev) are gateways of one provider, `decision`, the same way Claude/OpenRouter are gateways of `anthropic`.
4. Fallback is the agent wrapper's job for both kinds. Providers never chain.
5. Clean `src/` layout. Rename the service to **Legion** last.

## Roles

`role` is a required field in `agents/<id>.json`. It replaces `orchestrator`, `entry`, `delegable` and `internal_role`.

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

Two interfaces, no shared `run_chat`:

- `LanguageProvider.run_chat(...)`: tool loop, streaming, returns text. Unchanged behaviour.
- `DecisionProvider.answer(DecisionRequest) -> DecisionAnswer`: `{text, questions}` in, per question `{answer, confidence}` out. No text generation, no tools.

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
  agents/                       # what an agent is
    spec.py  config.py  registry.py  store.py  prompt.py  events.py
    roles/
      orchestrator/             # delegation, roster, plan, ask_user, memory/skill recall, summarizer
      router/                   # client, contract, engine, service, routing, auto_route
      specialist/               # scope + usability checks
  providers/                    # what an agent runs on
    base.py  failover.py  cooldown.py  cancellation.py  limits.py  tiers.py  reasoning.py
    language/
      anthropic/  openai/
    decision/
      provider.py  contract.py
      gateways/  laya.py  jev.py
  tools/                        # mcp_client + private_extensions
  runtime/                      # approvals, questions, broker, internal_auth, usage_log, tuning, config_files
```

Rules: `providers/` never imports `agents/`; `agents/roles/*` import `providers/` only through `base.py` types.
File moves keep git history (`git mv`).

## Config layout

- `gateways/language/{anthropic,openai}/*.json` (moved), `gateways/decision/{laya,jev}.json` (new).
- `agents/*.json`: add `role`; `provider: "laya"` becomes `provider: "decision", gateway: "laya"`; drop old flags.
- `configs/config_tuning.json`: remove `classifier.chains`, `triage_*` voter settings; keep per-feature enable/threshold under agent files or a slimmed section.

## Outside consumers to update

`ember_api`: `services/agent_directory.py`, `services/agent_admin.py`, `routes/triage_strategy.py`, tuning routes, `config.py`, `configs/config_app.json*`.
`ember_admin`: `AgentsAdminClient.ts`, `AgentForm.vue`, `AgentAdminCard.vue`, `TuningAdminView.vue`, `TuningClient.ts`, `e2e/router-agent.spec.ts`.
Also `docker-compose.yml`, `apps/armory` references, docs, the vault notes `Brain/Projects/MCPServer.md` and component notes, and `aiagent-scaffold` skill (both skill folders via `sync_skills.py`).

## Migration

Hard break, no compat shim. All 20 `agents/*.json` migrate in the same change set as the admin UI form, so no mixed state. Unknown keys already error loudly at supervisor start.

## Phases (each its own commit, tests green after each)

1. **Move**: restructure `src/` and `tests/` with no behaviour change; imports only.
2. **Role**: add `role`, remove four flags, migrate agent files, update ember_api/admin.
3. **Decision provider**: `DecisionProvider` + `laya`/`jev` gateways, wrapper-level fallback, delete `jev_vercel`, `laya_classifier`, `triage_flow`, `classifier.chains`; migrate triage/router/auto-tier/auto-route callers.
4. **Gateways folder**: split `gateways/` by kind.
5. **Rename**: `apps/garrison` to `apps/legion` (folder, compose service, env, docs, vault, skills).

## Risks and open checks

- Router and auto-tier callers use `decision.py` chains directly today; phase 3 must port each to the wrapper without changing their thresholds. Cases in `scripts/check_*` and `tests/test_router_*` are the regression net.
- Jev's `score`/`noul` answers come from a choice reduction; keep that mapping tested.
- Confirm the configured Laya strategy appears in `GET /v1/strategies` of the deployed service.
- Rename touches the docker network name and port env; verify `dev_deploy.bat` and the ZimaOS overlay.

## Testing

Existing suites move with their modules. New: role validation matrix, decision-provider contract tests with fake gateways, fallback order (error, unsupported, low confidence, `local_only`), agent-file migration check over all `agents/*.json`.
