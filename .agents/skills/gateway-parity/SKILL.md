---
name: gateway-parity
description: Use when adding or changing a feature, provider, gateway kind, request field, error kind, preset or limit in ConversationGateway or DecisionGateway (AI/ModelProviders), or when changing Legion's built-in copy in apps/legion/src/gateway, so the two stay aligned. Also use when asked whether Legion's gateways match the standalone ones.
---

# Gateway parity: standalone gateways and Legion's built-in copy

Legion runs its own copy of both gateways in `apps/legion/src/gateway/{conversation,decision}`. The standalone projects `AI/ModelProviders/ConversationGateway` and `DecisionGateway` stay for other callers. Nothing syncs them: a feature added to one is added to the other in the same sitting, or the difference is written in "Known differences" below. Read each project's own `AGENTS.md` first.

## File map (standalone `src/` -> Legion `src/gateway/<name>/`)

| Standalone | Legion copy |
|---|---|
| `service.py`, `store.py`, `contract.py`, `presets.py`, `failure.py`, `errors.py` | same names |
| `gateways/*.py` (adapters) | `gateways/*.py` |
| `answers.py`, `cache.py` (decision only) | same names |
| `config.py`, `options.py`, `runtime.py` | `settings.py`: only the limits (`Settings` dataclass); no env, no admin-editable options |
| `admin_api.py` helpers (`MAX_TOKEN`, `_valid_url`), `runtime.load/replace` | `src/gateway/shared.py` (`MAX_TOKEN`, `valid_url`, `load`, `replace`) |
| `gateways_api.py` (`FORM`, admin routes) | `src/gateway/routes.py` (`DECISION_FORM`, `/agents/model-gateways/...`); the chat `FORM` stays in `store.py` |
| `app.py`, `middleware.py`, `tokens.py`, `run.py`, `web/`, usage and backends | not copied: Legion has no HTTP hop, token or admin page of the gateway's own |
| `tests/test_{service,store,contract,<adapters>}.py` | `apps/legion/tests/gateway/<name>/` |

Copy rule: take the standalone file, rewrite `from src.X` to `from src.gateway.<name>.X` (`from src.config import Settings` -> `from src.gateway.<name>.settings import Settings`, `runtime.load/replace` -> `shared.load/replace`, `from src.admin_api import MAX_TOKEN, _valid_url` -> `from src.gateway.shared import MAX_TOKEN, valid_url as _valid_url`), and in copied tests also rewrite string paths used by `monkeypatch.setattr("src.service...")` to `src.gateway.<name>.service...`. Differences other than those rewrites need a reason in "Known differences".

## What else a change touches in Legion

| Change in the gateway | Also in Legion |
|---|---|
| New request field or chat option (`contract.py`) | The body builders of the shims: `src/providers/language/anthropic_gateway_shim.py`, `openai_gateway_shim.py`; `providers/gateway_client.py` only passes the body on |
| New decision question type or request field | `src/providers/decision/` (`contract.py`, `gateways/saved.py`, `gateway_client.py`) |
| New provider, kind, auth variant, field or preset (`store.py`, `presets.py`) | The form is read from `store.FORM` / `routes.DECISION_FORM`, so `ModelGatewayTable.vue` shows it with no change; add a test row in `apps/legion_admin/src/components/ModelGatewayTable.test.ts` only if it needs special handling. Presets that name a local service use `host.docker.internal`, never `127.0.0.1` |
| New error `kind` or retry rule (`errors.py`, `failure.py`) | `src/providers/gateway_failover.py` and the `GatewayCallError` mapping in `providers/gateway_client.py` |
| New environment variable the adapters read | Document it in `.env.gateways.example` and `docs/deployment.md` ("Model gateways"); only Legion loads `.env.gateways` |
| New dependency | `apps/legion/pyproject.toml` and `uv.lock` (`uv lock` in `apps/legion`) |
| New admin action (test, models list, delete) | `src/gateway/routes.py`, Portcullis `src/services/agent_admin.py` and `src/routes/agent_admin.py` (`/api/admin/model-gateways/...`, `agents.manage`), `AgentsAdminClient.ts`, the page |

## Steps

1. Change the project where the feature is wanted, with its tests.
2. Port the change to the other side using the file map; keep Legion's service API (`ChatService.stream/chat/gateways/models/test`, `DecisionService.decide/gateways/test`) unless the change is the API.
3. Port or add the tests (`apps/legion/tests/gateway/<name>/`). Run `uv run pytest tests/gateway tests/test_gateway_client.py tests/test_decision_gateway_client.py tests/test_model_gateway_routes.py` in `apps/legion`; run the standalone project's own tests there too.
4. Update both sides' docs: the standalone `README.md`/`CHANGELOG.md` and `docs/deployment.md` "Model gateways" in Citadel.
5. Finish with what was ported, what was not, and why.

## Known differences (on purpose)

- Legion's copy has no token layer, no admin password, no usage counters, no playground, no admin-editable settings, no `/health`.
- Limits come from the `Settings` defaults in `settings.py`; the standalone ones can be changed on its admin page or by `SERVICE_*` variables.
- `store.py` keeps entries (keys and tokens included, write-only) as rows of Legion's `settings.db` through `settings_store` (tables `conversation_gateways`, `decision_gateways`), not in a JSON file; a secret field may also hold `env:NAME`.
- All calls run on one background event loop (`src/gateway/__init__.py`: `call`, `call_sync`, `stream`) because the services hold loop-bound HTTP pools. Never create a service or call one from another loop directly.
