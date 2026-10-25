# Editable garrison tuning (ember_admin + ember_web)

## Goal
Let an administrator edit garrison's runtime tuning from ember_admin, and let each user set two of their own limits from ember_web Settings, without editing `configs/config_tuning.json` or restarting agents.

## Scope
This round: garrison `config_tuning.json` only. Armory, treasury and ember_api config are out; they can reuse the same overlay pattern later.

## Decisions
- Approach A. Garrison keeps no database.
  - Admin values live in a new overlay file `apps/garrison/configs/tuning_overrides.json`, written atomically by garrison.
  - Per-user values live in ember_api's DB, table `account_tuning`, and are sent to garrison with each chat call.
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
- New `src/core/tuning_overrides.py`: schema allowlist (type, min, max per key), `load()`, `save(patch)`, `reset(path)`, `effective()`.
  - Writes use the temp-file-and-replace pattern from `config_files.seed_tuning`.
  - An unreadable or invalid overlay is ignored, falls back to file defaults, and is logged.
- Readers (`token_limits.py`, `decision.py`, failover and classifier users) read through `effective()`. Each agent process checks the overlay's mtime on use and calls its own `reset_cache()` when it changed, so no cross-process signal is needed.
- Endpoints, internal-token protected like the existing admin routes:
  - `GET /admin/tuning` returns `{defaults, overrides, effective, schema}`.
  - `PUT /admin/tuning` takes a partial patch, validates it, saves, and returns `effective`.
  - `DELETE /admin/tuning?path=token_limits.default.max_tool_rounds` resets one key.
- Chat request accepts optional `limits: {max_output_tokens, max_tool_rounds}`; `token_limits.limits_for` applies `min(user, effective)`.

## ember_api
- Permission `tuning.manage` in `services/permissions.py`, added to the admin role set.
- `routes/admin_tuning.py` proxies the three endpoints through a `TuningAdmin` service modelled on `services/agent_admin.py` (502 when garrison is unreachable, garrison validation errors passed on as 400). Every change is written to the activity log with before and after.
- `routes/account_tuning.py`: `GET/PUT /api/account/tuning` reads and saves the account's two values, validated against the admin ceiling that the GET returns.
- Table `account_tuning(account_id pk, max_output_tokens null, max_tool_rounds null, updated_at)` via an Alembic migration. A null means "use the admin value".
- The chat proxy adds the account's `limits` to each request to garrison.

## UI
- ember_admin: a Tuning view under admin navigation, forms generated from the garrison `schema`; each field shows its default, a "changed" badge when overridden, and a reset button. Follows `ember-frontend-design` and `ember-design-system`.
- ember_web: a "Response limits" row in Settings with two number inputs; each shows the admin cap as its max, and a clear button.

## Errors
- Out-of-range or unknown key: 400 with the key path in the message.
- Garrison down: 502 in admin routes; the account GET still returns the stored values and marks the ceiling unknown, and the PUT is refused.
- Chat is never blocked by an invalid stored user value; garrison clamps it.

## Tests
- Garrison: schema validation, merge precedence, user clamp, atomic write, invalid-overlay fallback, mtime reload.
- ember_api: permission gate, activity log entry, proxy error mapping, account route ceiling check, migration up and down.
- Playwright: one spec for the admin Tuning view, one for the Settings row.

## Not checked or deferred
- Classifier edits change routing quality; no eval is run on save. Admin sees the file default beside each value to revert.
- No per-user classifier or failover control.
- Concurrent admin saves: last write wins.
