# Plan 4: Legion on DecisionGateway

Branch: `refactor/legion-decision-gateway`. Follows Plan 3b.

## Goal

Legion asks Laya and Jev through DecisionGateway (port 29406). Legion keeps the arrangement (`laya-only`, `jev-only`, `both`) and nothing else: no upstream address, key, model, strategy or window.

## Tasks

1. `src/runtime/gateway_settings.py`: a second record, `decision_gateway`, beside `conversation_gateway` (same Treasury collection, same rules). Environment fallback `DECISION_GATEWAY_URL` / `DECISION_GATEWAY_TOKEN`.
2. `src/providers/decision/gateway_client.py`: `decide()` (`POST /api/decide`), `saved_gateways()` (`GET /api/gateways`, 15 s cache), `is_usable()`, `is_reachable()`.
3. `src/providers/decision/gateways/saved.py`: `SavedGateway`; `laya()` is local with a 4000-character limit and a 60 s timeout, `jev()` is remote with a 3 s timeout. Delete `jev.py`, `laya.py`, `laya_model.py`.
4. Router status reads the gateway listing. Supervisor no longer checks the Laya strategy at start.
5. Routes `GET/PUT /agents/decision-gateway-settings` (Legion) and `/api/admin/decision-gateway-settings` (Portcullis, `agents.manage`). Legion admin **Connections** page shows one card per gateway (`GatewayConnectionCard.vue`).
6. `docker-compose.yml`: service `decisiongateway`, `DECISION_GATEWAY_ADMIN_PASSWORD`, port 29406 published, volume `decisiongateway_data`.
7. Docs and vault notes.

## Accepted behavior changes

1. Jev questions are sent in their native type. Legion no longer rewrites score and noul questions as a choice, and no longer spreads the remaining probability over the other options: the answer is what DecisionGateway returns.
2. Laya's strategy and window are set on the `laya` entry in DecisionGateway. `gateways/decision/*.json` keep only `label`. The start-up check "strategy is offered by the Laya service" is gone; a wrong strategy shows up as a refused request.
3. Which gateway is local is fixed by id: `laya` local, `jev` not. `local_only` requests rely on the `laya` entry really pointing at a local service.
4. A gateway is "available" when it is saved and not reported down. When DecisionGateway cannot be asked, it counts as available and the call itself reports the outage, so `both` still falls through. The router status page is stricter: `loaded` only when the listing says Laya is reachable.
5. Legion no longer retries a busy Laya service (429); DecisionGateway does that itself.
6. DecisionGateway caches answers for 300 seconds by default. The same text and questions inside that time return the cached answer.
7. `LAYA_SERVICE_URL`, `LAYA_TOKEN` and `TYPESAFE_API_KEY` are no longer read by Legion.

## Execution notes (2026-11-15)

- Executed in full. Legion suite: 1422 passed (1460 before; net 38 fewer: the tests of the deleted Jev mapping, Laya client, Laya gateway file and start-up check are gone, the client, saved-gateway and settings tests are new). Portcullis `test_agent_admin.py`: 12 passed. `legion_admin`: 76 passed, `vue-tsc` clean. `docker compose config` accepts the file.
- Not run: the full Portcullis suite before this note was written, Docker builds, any live call through DecisionGateway, the Connections page in a browser.
- `Laya.combine` and `Laya.validate` had no caller in Legion and were removed with the client.
