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

- **`laya`**: HTTP client for the `LayaModel` service (`LAYA_SERVICE_URL`, `LAYA_TOKEN`). The service owns weights, strategies and decision rules. Legion loads nothing. The agent's `model` field selects the service strategy (e.g. english, typed-decisions); names come from `GET /v1/strategies`.
- **`jev`**: TypeSafe cloud API (`POST /v1/systemone`, `TYPESAFE_API_KEY`). Stays cloud. Today it takes one `choice` question per call. It raises `UnsupportedQuestion` for `score`/`noul`, and the wrapper then falls to the next gateway.
- **Removed**: `jev_vercel`, `VERCEL_GATEWAY_API_KEY`, `laya_classifier` (the local 512-window backend), `triage_flow.py` voter mixing, `classifier.chains`.

### Fallback

Same mechanism for both kinds: `llm.fallback_gateways` is an ordered list of `{gateway, model?}`; the agent wrapper retries the next entry on gateway error, cooldown or unsupported question. The old triage order becomes agent config:

```json
"llm": {"provider": "decision", "gateway": "laya", "model": "english",
        "fallback_gateways": [{"gateway": "laya", "model": "typed-decisions"}, {"gateway": "jev"}]}
```

A `local_only` request skips any cloud gateway (`jev`) in the list.
Confidence thresholds (`min_confidence`) are checked by the wrapper: below threshold counts as "not settled" and moves on, as an error does.

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
- Jev supports only `choice` today; triage agents with `score`/`noul` questions depend on Laya gateways answering first.
- Laya strategy names must be confirmed against the running service before the agent-file `model` values are fixed.
- Rename touches the docker network name and port env; verify `dev_deploy.bat` and the ZimaOS overlay.

## Testing

Existing suites move with their modules. New: role validation matrix, decision-provider contract tests with fake gateways, fallback order (error, unsupported, low confidence, `local_only`), agent-file migration check over all `agents/*.json`.
