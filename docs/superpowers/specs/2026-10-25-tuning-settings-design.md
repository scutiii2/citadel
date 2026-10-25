# Editable garrison tuning (ember_admin + ember_web)

## Goal
Let an administrator edit garrison's runtime tuning from ember_admin, and let each user set two of their own limits from ember_web Settings, without editing `configs/config_tuning.json` or restarting agents.

## Scope
This round: garrison `config_tuning.json` only. Armory, treasury and ember_api config are out; they can reuse the same overlay pattern later.

## Decisions
- Approach A. Garrison keeps no database.
  - Admin values live in a new overlay file `apps/garrison/configs/tuning_overrides.json`, written atomically by garrison. It mirrors `src/agents/prompt_config.py` (`config_prompts.json`): the file holds only what an admin changed, as flat dotted paths (`"token_limits.default.max_tool_rounds": 20`).
  - Per-user values live in treasury through ember_api's `DocumentStore` (collection `tuning_limits`, key the account uid), the same way `nav_preferences` does. No Alembic migration. They are sent to garrison with each chat call.
- Precedence: `config_tuning.json` < admin overlay < user value, and a user value is clamped to the admin-effective value (the user can only lower).
- Keys not in the allowlist (URLs, models, chains, `triage_order`) stay file-only.

## Editable keys
| Section | Keys | Who |
|---|---|---|
| `token_limits` | `max_output_tokens`, `max_context_tokens`, `max_tool_rounds` (default, per provider, per gateway) | admin |
| `token_limits` | `max_output_tokens`, `max_tool_rounds` | user (own, lower only) |
| `gateway_failover` | the three `*_cooldown_seconds` | admin |
| `classifier` | `triage_thresholds`, `triage_enabled`, `timeout_seconds`, `max_input_chars`, `triage_fallback`, `triage_trace`, `triage_window`, `triage_prune_ratio`, `triage_pair_ratio` | admin |

## Garrison
- New `src/core/tuning_overrides.py` (stdlib only, like `prompt_config.py`): an allowlist of dotted paths with a type and range each, `load()`, `save(changes)`, `apply(raw, path)`, `signature()`, `poll()`.
  - Writes use the temp-file-and-replace pattern from `config_files.seed_tuning`. In Docker, the configs path links to `.data/admin_tuning_overrides.json` in the existing persistent `agent_data` volume; atomic writes preserve that link.
  - An unreadable or invalid overlay is ignored, falls back to file defaults, and is logged.
- `config_files.read_section` merges the overlay into `config_tuning.json` for every reader (`token_limits.py`, `decision.py`, `gateway_failover.py`), so no reader changes its parsing.
- Each cached reader registers its `reset_cache` with the overlay module. `run_chat` calls `tuning_overrides.poll()` at the start of a turn; when the overlay's mtime changed it runs the resets. No cross-process signal is needed.
- Endpoints, internal-token protected (under the `/agents` prefix already guarded by `PROTECTED_PATHS`):
  - `GET /agents/tuning` returns `{defaults, overrides, effective}`.
  - `PUT /agents/tuning` takes `{path: value | null}`; `null` resets a path. It validates, saves, and returns the same body as GET.
- `ask()` accepts optional `limits: {max_output_tokens, max_tool_rounds}`. The clamp is applied in `llm_options.max_tokens` and `max_tool_rounds`, because an agent file's `llm.max_tokens` overrides `token_limits` and would otherwise bypass a user limit. `status()` reports `user_limits: true` so ember_api only sends the field to an agent that understands it.

## ember_api
- Permission `tuning.manage` in `services/permissions.py`, added to the admin role set.
- `routes/admin_tuning.py` proxies GET/PUT through the existing `AgentAdmin` service in `services/agent_admin.py` (502 when garrison is unreachable, garrison validation errors passed on as 400). Every change is written to the activity log with before and after.
- `routes/account_tuning.py`: `GET/PUT/DELETE /api/account/tuning` reads, saves and clears the account's two values, validated against the admin ceiling that the GET returns.
- `services/tuning_limits_service.py` stores one document per account in treasury (`{owner, max_output_tokens, max_tool_rounds, updated_at}`); a missing field means "use the admin value".
- The turn adds the account's `limits` to `TurnOptions`, and `AgentGateway.ask` sends them when the agent's `status` has `user_limits`. If reading `tuning_limits` fails, the turn runs without user limits; the existing disabled-agents 503 remains unchanged.
- Delegated sub-agents run in other processes and do not receive the user's limits; they use the admin values.

## UI
- ember_admin: a Tuning view under admin navigation, with a fixed list of fields (labels, units and ranges kept in the view); each field shows its default, a "changed" badge when overridden, and a reset button. Follows `ember-frontend-design` and `ember-design-system`.
- ember_web: a "Response limits" row in Settings with two number inputs; each shows the admin cap as its max, and a clear button.

## Errors
- Out-of-range or unknown key: 400 with the key path in the message.
- Garrison down: 502 in admin routes; the account GET still returns the stored values and marks the ceiling unknown, and the PUT is refused.
- Chat is never blocked by an invalid stored user value; garrison clamps it. A stored user cap also follows a newly lowered admin ceiling when an agent file supplies its own limit.
- Only a failed `tuning_limits` read falls back to no user limits. The existing disabled-agents read remains closed on failure with 503.
- Voter switches are validated together against the file-only triage order; a change cannot disable its last usable voter.

## Tests
- Garrison: schema validation, merge precedence, user clamp, atomic write, invalid-overlay fallback, mtime reload.
- ember_api: permission gate, activity log entry, proxy error mapping, account route ceiling checks, storage and chat forwarding, and the tuning-only fallback with the disabled-agents 503 preserved. No migration is needed.
- UI: Vitest component and Settings integration tests plus one Playwright spec for the admin Tuning view and one for the Settings row, covering save/reset and draft retention. Both pages protect unsaved drafts on navigation.

## Not checked or deferred
- Classifier edits change routing quality; no eval is run on save. Admin sees the file default beside each value to revert.
- No per-user classifier or failover control.
- Concurrent admin saves: last write wins.
