# ConversationGateway and DecisionGateway inside Legion

## Goal
Legion runs both gateways in its own process. No gateway containers, host ports, access tokens, URL settings, `.env.gateways`, setup overlays, or ServiceHub entries. The gateway entries (which model, which provider key) are managed on a new Legion admin page.

## Decisions
- Gateway code is copied into `apps/legion/src/gateway/conversation/` and `apps/legion/src/gateway/decision/`. The standalone repos in `AI/ModelProviders` stay as they are for other projects; the copies are not kept in sync.
- Legion calls `ChatService` and `DecisionService` directly, through `src.gateway.chat_service()` and `decision_service()`, all running on one background loop (`gateway.call`, `call_sync`, `stream`). The HTTP hop, `X-Internal-Token`, and `/health` disappear.
- Entries (with their keys and tokens, write-only) are rows of Legion's settings database `.data/legion/settings.db`, tables `conversation_gateways` and `decision_gateways`, through `settings_store`. Treasury no longer holds gateway url or token.
- Provider keys are `env:NAME` references read from Legion's own environment. Legion's compose service loads the root `.env.gateways` (optional) as an extra `env_file`; no other service does.
- New admin page "Model gateways" in `legion_admin` replaces the gateway cards on Connections. It lists, saves, deletes and tests entries of both gateways. Portcullis passes the calls through to Legion, gated by `agents.manage`.

## Dropped from the copies
`app.py`, `middleware.py`, `tokens.py`, `run.py`, `admin_api.py`, `config.py` env settings that only served the HTTP server, `web/`, `Backends`, `Usage`, playground, MCP stub.

## Kept
`service.py`, `store.py`, `contract.py` (request parsing and limits), `gateways/*`, `presets.py`, `options.py` (limits), `failure.py`, `errors.py`, `runtime.py` where the services use it, `answers.py` and `cache.py` (decision).

## Interfaces
- `src/gateway/conversation/service.py`: `ChatService.stream(request)`, `.chat(request)`, `.gateways()`, `.models(id)`, `.test(id)`.
- `src/gateway/decision/service.py`: `DecisionService.decide(request)`, `.gateways()`, `.test(id)`.
- Legion's `providers/gateway_client.py` keeps `ConversationGatewayClient.stream/chat_sync`, `saved_gateway_ids`, `is_saved`, and `GatewayCallError`; the body now calls the service and maps `GatewayError` to `GatewayCallError` (`status`, `code`, `message`, `kind`, `retry_after`). `providers/decision/gateway_client.py` keeps `decide`, `saved_gateways`, `is_usable`, `is_reachable`.
- New Legion routes under `/agents/model-gateways/{conversation|decision}`: `GET` list, `PUT /{id}`, `DELETE /{id}`, `POST /{id}/test`, `GET /{id}/models` (conversation only). Portcullis mirrors them at the same path under `/api/admin/agents/...` like the other agent admin routes.

## Removed
- Compose: services `conversation-gateway`, `decision-gateway`, `docker-compose.gateway-admin.yml`, `docker-compose.gateway-hub.yml`, `.env.gateways.example`, `CONVERSATION_GATEWAY_*` and `DECISION_GATEWAY_*` env vars, `llm_net` if nothing else uses it.
- Legion: `runtime/gateway_settings.py`, `/agents/gateway-settings*` routes, `connection_probe.probe_gateway`, the Connections gateway cards and their Portcullis passthroughs.
- Docs: the ConversationGateway and DecisionGateway sections of `docs/deployment.md` become "Model gateways" (add entries on the admin page, keys in `apps/legion/.env`).

## Dependencies added to Legion
`anthropic[bedrock,vertex]>=0.40`, `openai>=1.66`, `httpx2>=2` (ConversationGateway), `httpx` already present.

## Migration
Entries are not imported: re-add them on the page (the old `gateways.json` files list what they were). Keep the provider keys in `.env.gateways` (Legion now loads it). Decision `laya` URL stays `http://host.docker.internal:29220`; Legion's container needs `extra_hosts: host.docker.internal:host-gateway`.

## Risks
- Chat streaming now shares Legion's event loop; the services are async and already non-blocking.
- Copied code drifts from the standalone repos. Accepted.
- Entries with the old `host.docker.internal` hosts need that `extra_hosts` line on Legion.

# Plan

Tests per task only; run with `uv run pytest <file>` in `apps/legion` (admin: `pnpm exec vitest run <file>`).

### Task 1: Vendor the services
- Copy the "Kept" files into `src/gateway/conversation/` and `src/gateway/decision/`; rewrite `from src.` imports to `from src.gateway.<name>.`; add `src/gateway/__init__.py` and the new dependencies to `pyproject.toml`.
- Copy their tests for `service`, `store`, `contract`, and the provider adapters (`test_anthropic`, `test_openai`, `test_scuti`, `test_typesafe`, `test_ollama`, `test_freellmapi`, `test_answers`) into `tests/gateway/<name>/`; fix imports.
- Run: `uv run pytest tests/gateway`.

### Task 2: Store location and wiring
- `src/gateway/__init__.py`: `conversation_service()` and `decision_service()` build one store and one service each, from `.data/gateways/*.json` under Legion's data dir, with limits from defaults. Closed at Legion shutdown.
- Test: `tests/gateway/test_wiring.py` (service built, store path, shutdown closes).

### Task 3: Legion clients call the services
- Rewrite the HTTP bodies of `providers/gateway_client.py` and `providers/decision/gateway_client.py` to call the services; map `GatewayError`. Keep every public name.
- Update `tests/` that used `_SYNC_TRANSPORT` or fake gateway HTTP to inject a fake service.
- Run the existing client test files.

### Task 4: Admin routes in Legion and Portcullis
- Legion `server.py`: the routes listed under Interfaces. Portcullis `agent_admin` service and routes: passthroughs, `agents.manage`.
- Tests: `apps/legion/tests/test_model_gateway_routes.py`, `apps/portcullis/tests/test_agent_admin.py`.

### Task 5: Admin page
- `legion_admin`: `views/ModelGatewaysView.vue`, nav entry, `AgentsAdminClient` methods, a `RecordDrawer` form per entry (id, provider, model, key as `env:NAME`, URL where the provider needs one), Test button per row (reuse `ConnectionTest.vue`).
- Remove the gateway cards from `ConnectionsView.vue`.
- Test: `ModelGatewaysView.test.ts`, `ConnectionsView.test.ts`.

### Task 6: Remove the old path
- Delete `gateway_settings.py`, its routes and tests, `probe_gateway` and its test, the Portcullis gateway-settings passthroughs and the Legion admin client methods.
- Compose: remove both services and both overlay files, `.env.gateways.example`; add `extra_hosts` to `legion`; drop `llm_net` if unused. Update `docs/deployment.md`, `apps/legion/AGENTS.md`, and skills that mention the gateways.
- Run: `uv run pytest tests/test_connection_probe.py` in `apps/legion` and the touched admin tests.
