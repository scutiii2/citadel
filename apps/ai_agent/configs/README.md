# configs/

Startup configuration for this `ai_agent` instance: hand-edited, read once
when the process starts. Missing files are seeded; legacy tuning is migrated
on first read. Never credentials
(those go in `../.env`). Anything the program itself writes while running
lives under `../.data/` instead (see the end of this file).

- **`config_tuning.json`** - `token_limits`: output/context/tool-round
  caps, per provider and gateway (`src/llm/token_limits.py`). `classifier`
  (the `.example` seeds every key at its default, so every feature is off until you switch it on; a key
  you delete falls back to that default): the decision layer
  (`src/llm/decision.py`) - `triage_fallback`, `triage_trace` (full instead of compact answers), `triage_window`, `triage_thresholds`, `triage_enabled` (voter -> question type -> on/off), `triage_order` (question type -> voters, first to last),
  `triage_prune_ratio`, `triage_pair_ratio`, `chains` (feature: backends tried in
  order; `jev`, `jev_vercel`, `laya`), `typesafe` and `vercel` (`url`, `model`),
  `timeout_seconds`, `max_input_chars`, `auto_tier` (`enabled`,
  `min_confidence`, `tiers`: the model tier chosen per request size) and `auto_route`
  (`enabled`, `min_confidence`: send a question straight to a specialist). Needs
  `TYPESAFE_API_KEY` or `VERCEL_GATEWAY_API_KEY` in `../.env`, per the chain.
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
real files are gitignored (`/apps/ai_agent/configs/*` and the root `config_*.json`
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
