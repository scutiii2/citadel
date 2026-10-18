# Usage cost beside the token count

**Goal:** show a money cost next to every token count in ember_web (answer chip, chip panel, Usage page). Cost = tokens x a per-model price from an editable JSON table in ember_api.

**Decisions (user-approved)**
- Price table lives in ember_api config, editable JSON, USD per 1M tokens, separate input and output price per model.
- API computes cost on read. Nothing is stored, no migration, so editing prices also re-prices old answers.
- Unknown model or missing token split gives `null` cost. The UI then shows no cost. Never show a fake `$0`.
- ember_admin is out of scope (optional follow-up, same pattern).
- No reduced-motion anything (repo rule). Plain file names, no dot prefix (`configs/config_pricing.json`).

## Where things are today
- Chip text: `apps/Ember/ember_web/src/utils/usageFormat.ts` `usageSummary()` (tokens as `compactNumber(m.total_tokens) tokens`). Panel rows: `src/components/UsageChip.vue` `rows`, per-agent line via `agentUsageText()`.
- Message and agent_usage types: `ember_web/src/api/types.ts` (`ChatMessage` ~line 42, `AgentUsage` ~line 84).
- Usage page: `ember_web/src/views/UsageView.vue`, types in `src/api/UsageClient.ts` (`UsageGroup`, `UsageRecordRow`, `UsageReport`), export in `src/utils/usageExport.ts`.
- API settings: `ember_api/src/config.py` (`UsageSettings`, `Settings`, `load_settings`), config loader `src/utils/config_loader.py` `load_json_config` (creates file from `.example` if missing).
- Usage reports: `ember_api/src/services/usage_service.py` `report()` and `records()`; routes `src/routes/usage.py` (`UsageRecordOut`, `UsageOut.report` is a free `dict`).
- Chat messages are stored as JSON dicts and served raw: `routes/chats.py` `ChatOut.of()` returns `decode_messages(chat)`. The live answer reaches the browser as the SSE `final` event `message` built in `services/turns.py` (~line 663-682). Both paths must carry cost.

## Task 1 - ember_api: price table and cost function
Files: `configs/config_pricing.json`, `configs/config_pricing.json.example`, `src/config.py`, new `src/services/pricing.py`, new `tests/test_pricing.py`, `configs/README.md`, `README.md`.

1. `config_pricing.json.example`:
   ```json
   {
     "currency": "USD",
     "models": {
       "example-model": { "input": 0.0, "output": 0.0 }
     }
   }
   ```
   Prices are USD per 1,000,000 tokens. Do NOT invent real prices; ship the example with the placeholder entry and tell the user to fill real model names and prices. Create a local `config_pricing.json` copy only if the loader requires it (it auto-copies from the example).
2. `config.py`: add frozen dataclass `PricingSettings` with `currency: str = "USD"`, `models: dict[str, ModelPrice]`, `ModelPrice(input: float, output: float)`; `from_config(raw)` validates: prices are numbers >= 0, model keys non-empty strings, else `ValueError` naming the key. Add `pricing: PricingSettings` to `Settings`; `load_settings()` loads it with `load_json_config(CONFIGS_DIR / "config_pricing.json")`.
3. `pricing.py`: class `Pricing` (built from `PricingSettings`), method
   `cost(model: str | None, input_tokens: int | None, output_tokens: int | None) -> float | None`:
   - `None` if model is falsy or not in the table, or both token counts are `None`.
   - Treat one missing side as 0 only if the other is present.
   - Lookup is exact first, then case-insensitive. Result `(in*p_in + out*p_out) / 1_000_000`, not rounded (UI formats).
   Also `currency` property. Add `aggregate(items)` helper only if Task 2 needs it: sum of non-null costs, `None` if all null.
4. Tests (`tests/test_pricing.py`): known model, unknown model gives None, missing tokens, one side missing, case-insensitive match, config validation errors (negative price, non-number).
5. Document the file in `configs/README.md` and the API README (units: USD per 1M tokens, unknown model shows no cost).

Done when: `pytest tests/test_pricing.py` passes and `load_settings()` loads with only the example present.

## Task 2 - ember_api: put cost on the wire
Files: `src/deps.py` (provider `get_pricing`), `src/routes/chats.py`, `src/services/turns.py`, `src/services/usage_service.py`, `src/routes/usage.py`, tests `tests/test_chats.py`, `tests/test_usage*.py`.

1. Add `get_pricing(settings)` dependency in `deps.py`; construct `Pricing` once (cached on `app.state` or built from settings, follow how `get_settings` is done).
2. Chat messages: new helper `with_cost(message: dict, pricing) -> dict` that adds `cost` (float) to the message from `model/input_tokens/output_tokens`, and `cost` to each `agent_usage` entry. Omit the key when cost is `None`. Never persist: apply only on output.
   - `ChatOut.of()` / `get_chat` route: map `with_cost` over `messages`.
   - `turns.py` `final` event (~line 680): apply `with_cost` to the message sent in the event only, not to the one saved by `replace_messages`. TurnRegistry needs the `Pricing`; pass it in where it is constructed (check `get_turns` in `deps.py`).
   - Any other route that returns stored messages to the browser (grep `decode_messages` in `routes/`) gets the same mapping; branch/import responses too if they return messages.
3. Usage records: `UsageRecordOut` gets `cost: float | None`; `UsageRecordOut.of(row, pricing)` computes it. Update the two `of(...)` call sites in `routes/usage.py`.
4. Usage report: `UsageService` takes `Pricing` (constructor arg; update `get_usage_service`). In `report()` compute per-row cost inside the existing loop (it already has `model`, `input_tokens`, `output_tokens`):
   - add `cost` to each `groups` entry, `cost` to `by_agent` entries, and `total_cost` plus `currency` at report top level. `cost` is `None` when no row in that bucket was priceable.
   - Also add `unpriced_tokens` (tokens from rows with `None` cost) to the report so the UI can say the total is partial.
5. Admin routes reuse `my_usage` so they get cost for free; `all_accounts` stays tokens-only (out of scope).
6. Tests: seed rows with a priced and an unpriced model, assert group cost, `total_cost`, `unpriced_tokens`, record `cost`, a chat GET message `cost`, an agent_usage entry `cost`, and that the stored message JSON has NO `cost` key.

Done when: API tests pass and a manual `GET /api/usage` shows `total_cost`.

## Task 3 - ember_web: types, format helper, chip
Files: `ember_web/src/api/types.ts`, `src/api/UsageClient.ts`, `src/utils/usageFormat.ts`, `src/components/UsageChip.vue`, tests `usageFormat.test.ts`, `UsageChip.test.ts`.

1. Types: `ChatMessage.cost?: number`, `AgentUsage.cost?: number`, `UsageGroup.cost: number | null`, `UsageRecordRow.cost: number | null`, `UsageReport.total_cost: number | null`, `currency: string`, `unpriced_tokens: number`, `by_agent[].cost`.
2. `usageFormat.ts`: `formatCost(cost: number, currency = "USD"): string` using `Intl.NumberFormat`:
   - `0 < cost < 0.0001` gives `<$0.0001`; under $0.01 show 4 decimals; under $1 show 3; otherwise 2.
   - Keep it a pure function with unit tests for each band and a non-USD currency.
3. `usageSummary()`: after the tokens part add `formatCost(m.cost)` when `m.cost !== undefined`, e.g. `agent · model · 12.4k tokens · $0.042 · 4.2 s`. Command and triage branches unchanged.
4. `agentUsageText()`: append the cost after `total` when present.
5. `UsageChip.vue` rows: add `{ label: "Cost", value: formatCost(m.cost) }` after "Total tokens" when present. Add a short note on the panel if the cost is only for part of the answer is NOT needed (per-agent costs already listed).
6. Tests: summary with and without cost, panel row, agent line.

Done when: `npm run test` (vitest) and `npm run type-check` pass in `ember_web`.

## Task 4 - ember_web: Usage page and export
Files: `src/views/UsageView.vue`, `src/utils/usageExport.ts`, `src/views/UsageView.test.ts`, `src/utils/usageExport.test.ts`, `e2e/fakeApi.ts`.

1. Stat row (`UsageView.vue` ~line 228): add a stat `formatCost(total_cost)` labelled "cost" when `total_cost !== null`. When `unpriced_tokens > 0` add a muted note "Excludes N tokens from models with no price."
2. Groups table (~line 266): add a cost column; show an em dash when `cost` is null. Follow existing table styles and the repo radius tokens; reuse `num` class.
3. Per-turn list (~line 297): show the sum of row costs beside `turn-total` when any row has a cost (compute in the same place `total` is computed, line ~128).
4. `usageExport.ts`: add Total cost row and a cost column; null becomes empty.
5. `e2e/fakeApi.ts`: add `cost`/`total_cost`/`currency`/`unpriced_tokens` to the fake responses so the e2e page renders both a priced and an unpriced case.
6. Update view and export tests.

Done when: `npm run test`, `npm run type-check`, `npm run build` pass; open the Usage page against the fake API and confirm cost stat, column, partial-total note. (Per user preference, do not spawn browser-verification agents; user tests manually.)

## Task 5 - docs and vault
- Update `apps/Ember/ember_api/README.md` and `configs/README.md` (done in Task 1; check).
- Update `Brain/Projects/MCPServer.md` / `ember_api.md` notes only if asked (project sync).
- Run `python sync_skills.py --check`; touch no skills unless a skill describes the usage payload.

## Order and risk
Tasks 1 -> 2 -> 3 -> 4 in order (each depends on the previous). Task 2 step 2 (all paths that return stored messages) is the one most likely to miss a spot: grep `decode_messages` and the SSE `final` event and test each. Streaming answers already shown in the browser get cost from the `final` event, so the chip needs no extra fetch.

## Open items for the user
- Real model names and USD prices to put in `config_pricing.json` (the plan ships placeholders only).
- ember_admin cost display (follow-up).
