# Triage strategy: per-user choice (ember_web) and admin default (ember_admin)

## Goal
A user picks which LayaAgent decision strategy answers their prompts sent straight to the Triage Assistant from ember_web. An administrator sets the default strategy in ember_admin. The default applies to every LayaAgent caller, not only Ember.

## Scope
- In: Garrison strategy resolution, a one-key admin overlay, ember_api admin and account routes, ember_web Settings row, ember_admin control.
- Out: the rest of `2026-10-25-tuning-settings-design.md` (token limits, failover, classifier keys). This slice is built so that spec later absorbs it.
- The orchestrator's own triage calls use the admin default but have no per-user choice.

## Background
- ember_web calls `/api/triage/ask`. ember_api (`services/triage_questions.py`) builds a `local_only` request for Garrison's Laya agent.
- `TriageFlow._ask_locals` (`apps/garrison/src/llm/triage_flow.py`) derives the strategy from `triage_order` and `triage_enabled`, so it only ever sends `english-then-typed`, `typed-then-english`, `english-only` or `typed-only`.
- The LayaAgent service supports 8 strategies and lists them at `GET /v1/strategies`: the 4 above plus `most-confident`, `average`, `consensus` and `auto` (the service default).

## Decisions
- Strategy names come from the service (`GET /v1/strategies`), never a copy in Garrison or Ember.
- Resolution order: request `strategy`, then admin default, then current behaviour (derived from voter config). An unset admin default keeps today's behaviour.
- Admin default is stored in Garrison (`configs/tuning_overrides.json`), so it covers every caller. Per-user value is stored in ember_api's DB. A null user value means "use the admin default".
- Jev fallback after an uncertain result is unchanged.

## Garrison
- `LAYAAgent.strategies()` calls `GET /v1/strategies` and returns `{strategies, default}`.
- The request JSON accepts optional `strategy`. `laya_provider.parse_request` rejects an unknown name with 422 (`Invalid Laya request`).
- `TriageFlow._ask_locals`: when a strategy resolves, all questions in the request go to the service in one call under that strategy. Otherwise the existing grouping runs.
- New `src/core/tuning_overrides.py`: holds `triage_strategy` only. `load()`, `save(patch)`, atomic write with the temp-file-and-replace pattern of `config_files.seed_tuning`. An unreadable or invalid file is ignored and logged. File shape: `{"classifier": {"triage_strategy": "..."}}`, so the full tuning spec reuses it.
- Internal-token endpoints:
  - `GET /admin/triage-strategy` returns `{default, strategies}` (`default` null when unset).
  - `PUT /admin/triage-strategy` takes `{strategy: str | null}`, validates against the service list, saves, returns the same shape. Null clears the override.

## ember_api
- Permission `tuning.manage` in `services/permissions.py`, in the admin role set.
- `routes/admin_triage_strategy.py` proxies GET and PUT through a service modelled on `services/agent_admin.py`. 502 when Garrison is unreachable; Garrison validation errors pass on as 400. Each change is written to the activity log with before and after.
- Table `account_tuning(account_id pk, triage_strategy null, updated_at)` via Alembic migration. The tuning spec's migration later adds columns to this table.
- `GET /api/account/triage-strategy` returns `{value, default, strategies}`. `PUT` takes `{value: str | null}` and validates against the strategy list. Garrison down: GET returns the stored value with `strategies: []`; PUT is refused with 503.
- `TriageQuestions.ask` adds `strategy` to the Laya request JSON only when the account value is set. ember_web never sends it.
- A stored value the service no longer lists fails with 503 from Garrison; there is no silent fallback.

## UI
- ember_web Settings: a "Triage strategy" row, dropdown with "Default (<admin's choice>)" first, then the strategies with their call cost (1 call, 1-2+, 2).
- ember_admin: a "Triage strategy" control with a dropdown and Save. "Auto (service default)" clears the override.
- Both follow `ember-frontend-design` and `ember-design-system`. No reduced-motion handling (`AGENTS.md`).

## Tests
- Garrison: resolution order, 422 on unknown name, overlay round-trip and atomic write, invalid-overlay fallback, endpoints.
- ember_api: permission gate, activity log entry, 502 mapping, account PUT validation, `ask` sends `strategy` only when set, migration up and down.
- Vitest: the Settings row and the admin control.

## Not checked or deferred
- No eval of how each strategy changes answer quality; the choice is the user's or admin's.
- Last write wins on concurrent admin saves.
- Per-user choice for orchestrator triage calls.
