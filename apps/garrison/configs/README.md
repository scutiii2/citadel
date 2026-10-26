# configs/

Startup configuration for this `ai_agent` instance: hand-edited, read once
when the process starts. Missing files are seeded; legacy tuning is migrated
on first read. Never credentials
(those go in `../.env`). Anything the program itself writes while running
lives under `../.data/` instead (see the end of this file).

`config_tuning.json` also accepts `gateway_failover`: `quota_cooldown_seconds`
and `auth_cooldown_seconds` default to 3600; `unavailable_cooldown_seconds`
defaults to 30. Rate limits use Retry-After or 60 seconds. Cooldowns are
per provider and gateway, in memory, and reset on process restart.
Choose backups with each agent's `llm.fallback_gateways` list, documented in
[`../README.md`](../README.md#gateway-failover); this tuning section only controls
the cooldown durations, and enables no backups by itself.

- **`config_tuning.json`** - `token_limits` supplies output/context/tool-round caps
  per provider and gateway (`src/providers/token_limits.py`). `classifier` supplies
  `timeout_seconds`, `max_input_chars`, and `auto_tier` / `auto_route` settings:
  `enabled`, `strategy` (`laya-only`, `jev-only`, `both`), and `min_confidence`
  (0-100). Auto tier also maps request sizes to model tiers. Features default off;
  the example selects confidence 80. Gateway endpoints/models live in
  `gateways/decision/`, and Laya's internal service strategy is read there on
  every call. It has no account or admin override.
- **`config_servers.json`** - `servers`: the MCP servers this agent
  connects to as a client (currently just `main`, this repo's
  `mcp_server`). Loaded by `src/mcp_client/config.py`'s `load_servers_config` into
  typed `ServerConfig` entries; each entry is `{label, description,
  transport, url|command, auth?}`, symmetric for every configured server
  unlike `mcp_server`'s own `config_extensions.json`.
- **`config_prompts.json`** - the prompt text every agent shares: `app_name`,
  `app_description`, `identity_template` (placeholders `{app_name}`,
  `{app_description}`, `{role}`), `default_instructions`, `roster_intro`,
  `caveman_instructions` (`src/agents/prompt_config.py`, used by
  `src/llm/agent_roles.py`). Holds only what differs from the built-in
  defaults, so a missing file means no change. Written by the admin UI
  (`PUT /agents/prompts`); the supervisor restarts every agent when it changes.
- Gateway presets live in [`../gateways/`](../gateways/README.md), one
  `<provider>/<gateway>.json` file each. The old `config_gateways.json` is
  migrated on first read and retained only as a rollback backup.

The tuning and server files have committed `.example` twins with
the same shape. Prompt overrides use built-in defaults and need no example;
the admin UI creates `config_prompts.json` when a prompt is customized. The
real files are gitignored (`/apps/garrison/configs/*` and the root `config_*.json`
rule), so a fresh checkout seeds each one from its `.example` twin on
first read, same as `../.env`.

On the first read of `config_tuning.json`, an existing `config_limits.json`
section takes precedence over example defaults. The old file is retained
as a backup and is no longer read once the merged file exists. Edit `config_tuning.json` and restart agents
to change tuning. A malformed legacy JSON file stops migration so settings
are not silently replaced. To roll back, use the previous code with the
retained file; copy back any settings changed after migration.

## Runtime state (not config)

- **`../.data/agent_registry.json`** - the `ai_agent` instances currently
  running, which `delegate_to_agent` (`src/agents/delegation.py`,
  `src/agents/agent_registry.py`) and ember_api read. Each instance upserts its
  own `{id, label, url, entry, orchestrator, focus}` on startup and removes
  it on clean shutdown, so never edit it by hand. Gitignored with the rest
  of `.data/`; created on first start.

## tuning_overrides.json

Written by the admin Tuning page (ember_admin), not by hand. It holds only what an admin
changed, as flat dotted paths such as `"token_limits.default.max_tool_rounds": 20`, and is
merged over `config_tuning.json` when that file is read. Delete a line (or reset it on the page)
to go back to the file's value. Gitignore it like the other local configs. Keys that are not
listed in `src/runtime/tuning_overrides.py` stay file-only, including feature enable flags and tier mappings.
Each agent process notices a change at the start of its next turn; no restart is needed.

In Docker, this path links to `.data/admin_tuning_overrides.json` in the existing `agent_data` volume.
The tuning overlay survives container recreation.
