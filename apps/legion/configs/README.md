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
- **The MCP servers are not here.** The servers this agent connects to as a client are the `servers` table of
  `.data/legion/settings.db`. A new install defaults `main` to Armory from the service catalog. An administrator may save a different `main` URL or add other servers. `GET /agents/servers` lists them, `PUT`/`DELETE /agents/servers/{id}`
  change them (a restart applies the change). Loaded by `src/tools/mcp_client/config.py`'s `load_servers_config`
  into typed `ServerConfig` entries; each entry is `{label, description,
  transport, url|command, auth?}`.
- **`config_prompts.json`** (in `.data/legion/`, not here) - the prompt text every agent shares: `app_name`,
  `app_description`, `identity_template` (placeholders `{app_name}`,
  `{app_description}`, `{role}`), `default_instructions`, `roster_intro`,
  `caveman_instructions` (`src/agents/prompt_config.py`, used by
  `src/agents/agent_roles.py`). Holds only what differs from the built-in
  defaults, so a missing file means no change. Written by the admin UI
  (`PUT /agents/prompts`); the supervisor restarts every agent when it changes.
- Gateway presets live in [`../gateways/`](../gateways/README.md), one
  `<provider>/<gateway>.json` file each. The old `config_gateways.json` is
  migrated on first read and retained only as a rollback backup.

Every file here is tracked and none has an `.example` twin. Edit
`config_tuning.json` and restart agents to change tuning. What an admin
changes on the Tuning and Prompts pages is runtime state, kept in
`.data/legion/` in the Citadel folder (see below), not in this folder.


## Runtime state (not config)

- **`.data/legion/agent_registry.json`** (Citadel folder) - the `ai_agent` instances currently
  running, which `delegate_to_agent` (`src/agents/delegation.py`,
  `src/agents/agent_registry.py`) and portcullis read. Each instance upserts its
  own `{id, label, url, entry, orchestrator, focus}` on startup and removes
  it on clean shutdown, so never edit it by hand. Not tracked: it is in
  of `.data/`; created on first start.

## tuning_overrides.json

Lives at `.data/legion/tuning_overrides.json`. Written by the admin Tuning page (stronghold_admin), not by hand. It holds only what an admin
changed, as flat dotted paths such as `"token_limits.default.max_tool_rounds": 20`, and is
merged over `config_tuning.json` when that file is read. Delete a line (or reset it on the page)
to go back to the file's value. Keys that are not
listed in `src/runtime/tuning_overrides.py` stay file-only, including feature enable flags and tier mappings.
Each agent process notices a change at the start of its next turn; no restart is needed.
In Docker the `.data/legion` folder is bind-mounted, so the overlay survives container recreation.

Treasury bootstrap address lives in tracked `configs/config_app.json` as `treasury_url`; `TREASURY_URL` overrides it. Legion entry agents register their base address in Treasury’s catalog. Treasury Admin, Services controls address pins; Legion Admin no longer edits Treasury’s address.
