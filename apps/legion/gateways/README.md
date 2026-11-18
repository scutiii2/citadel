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
  "model": "claude-sonnet-5",
  "models": {
    "light": {"id": "claude-haiku-4-5", "use_for": "quick tasks"},
    "standard": {"id": "claude-sonnet-5", "use_for": "most tasks"}
  }
}
```

Files in `anthropic/` and `openai/` hold only `label`, `prompt_cache`, `model` and `models`. Their connection and key are saved in ConversationGateway (`AI/ModelProviders/ConversationGateway`, admin page `/admin/gateways.html`) under the same id as the filename.

A model id may be an `{ENV_VAR_NAME}` placeholder (Azure deployment names); the value belongs in `../.env`. An `anthropic`
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
For rollback, use the previous code with the retained
legacy file; copy any subsequent gateway changes back into that file first.

## decision

Provider folder `decision/` holds `laya.json` and `jev.json`, each with only a `label`. The two
ids name entries saved in DecisionGateway (`AI/ModelProviders/DecisionGateway`): `laya` is the
local Laya model service, `jev` is TypeSafe's cloud API. Address, key, model, strategy and window
are set there. Agents choose `laya-only`, `jev-only` or `both`; that arrangement stays in Legion.
