# gateways/

One tracked gateway preset per `gateways/<provider>/<gateway>.json`, beside
`agents/`. The directory name is the provider protocol (`anthropic` or
`openai`, or `decision`); the filename without `.json` is the gateway id used by an agent's
`llm.gateway`. A gateway supporting both protocols can have a file in each
provider directory. Decision has `laya.json` and `jev.json`; agents select an
arrangement strategy instead of a single `llm.gateway`.

Each file contains the gateway block directly, without provider or gateway
wrapper keys. For example, `anthropic/claude.json`:

```json
{
  "label": "Claude",
  "api_key": "{CLAUDE_API_KEY}",
  "model": "claude-sonnet-5",
  "models": {
    "light": {"id": "claude-haiku-4-5", "use_for": "quick tasks"},
    "standard": {"id": "claude-sonnet-5", "use_for": "most tasks"}
  }
}
```

Use `{ENV_VAR_NAME}` placeholders for credentials; the actual values belong
in `../.env`. Files can also specify gateway-specific fields such as
`base_url`, `auth_token`, `azure_endpoint`, or `aws_region`. An `anthropic`
gateway that serves Claude models can set `"prompt_cache": true` to cache its system prompt,
tool list and conversation so far between calls (leave it off for gateways that route to other models). Optional `models`
defines the `light`, `standard`, `heavy`, and `extreme` tiers. Agent files keep their
existing `llm.provider` and `llm.gateway` values.

On first read, `src/providers/llm_config.py` splits an existing
`../configs/config_gateways.json` into individual files, preserving custom
gateways and leaving existing individual files untouched. It validates the
complete legacy configuration before publishing files, and retains the old
file as an unused rollback backup. Individual files take precedence over the old configuration; legacy-only
gateways are added without overwriting the tracked presets.

Gateway JSON files are committed directly and read without seeding or
`.example` copies. Adding, removing, or editing a preset produces a Git
change. Keep literal credentials out of these files.

Initialization writes the ignored `.initialized` marker only after legacy
migration completes. Keep this marker: it prevents later startups from
rereading the backup or recreating gateways you deliberately removed.
Temporary migration files are also ignored.

The gateway loader and admin catalog cache normal presets for the process
lifetime. Restart the agent processes and supervisor after editing those files.
Laya service strategy is the exception: `gateways/decision/laya.json` is read
on every call, so editing its strategy needs no restart. For rollback, use the previous code with the retained
legacy file; copy any subsequent gateway changes back into that file first.

## decision

Provider folder `decision/` holds `laya.json` and `jev.json`. Laya is the
local LayaModel service; its `strategy` selects any name offered by the
service's `GET /v1/strategies` endpoint (default `english-then-typed`). The
service URL is configured through `LAYA_SERVICE_URL`.

Jev calls the TypeSafe API; its URL and model are preset in `jev.json`, and
its credential is resolved from `TYPESAFE_API_KEY`.
