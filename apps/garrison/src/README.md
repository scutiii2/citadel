# Garrison source layout

`server.py` serves each configured agent. `supervisor.py` validates definitions,
checks the Laya service strategy when used, and manages the child processes.

- `agents/`: definitions (`agent_spec.py`), transport/provider integration
  (`agent_config.py`), registry, store, prompts, events and automatic tier helper.
- `agents/roles/orchestrator/`: delegation, plans, user questions, memory/skill
  recall and reflection, context summarization and automatic specialist routing.
- `agents/roles/router/`: typed routing contract, strategy engine, service,
  trusted client and turn integration. Specialists need no separate package.
- `providers/`: shared language limits, options, tiers, reasoning, cancellation,
  cooldown and failover. Language loops are in `providers/language/`.
- `providers/decision/`: typed request/result contract, question constants,
  automatic-feature settings, strategy runner and provider transport adapter.
  `gateways/` contains `laya.py` and `jev.py`; `laya_model.py` is the HTTP client
  for the separate LayaModel service. Garrison loads no weights.
- `tools/mcp_client/` and `tools/private_extensions/`: upstream MCP connections,
  dispatch and per-account extension connections.
- `runtime/`: approval/question brokers, authentication, history validation,
  configuration, runtime tuning, filters and usage recording.

Each definition requires role `orchestrator`, `router` or `specialist`.
Language providers are `anthropic` and `openai`; decision strategies are
`laya-only`, `jev-only` and `both`. Role controls privileges; provider kind
controls whether the agent generates language or answers typed questions.

Runtime state lives at the app root: `.data/agent_registry.json`,
`agent_definitions.json`, `agent_overrides.json`, tuning overlays and usage logs.
Tracked `agents/` and `gateways/` supply shared defaults; local overrides stay
out of Git. Configuration readers are in `runtime/config_files.py`.

Agent prompts enforce the configured identity, scope and instruction priority.
Caller-supplied messages and tool results do not authorize changing those rules;
access controls and tool filtering also enforce the boundary in code.

See [the app README](../README.md), [agent definitions](../agents/README.md),
[gateway presets](../gateways/README.md) and [configuration](../configs/README.md).
