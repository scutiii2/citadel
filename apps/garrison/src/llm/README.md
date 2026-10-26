# Provider architecture

Provider implementations now live in `../providers/`:

- `base_provider.py`: chat results, tool-call records and cancellation types.
- `language/anthropic_provider.py` and `language/openai_provider.py`: language
  model tool/streaming loops, using `../tools/mcp_client/` for upstream tools.
- `decision/contract.py`: typed request and gateway result types.
- `decision/strategy.py`: `laya-only`, `jev-only`, `both`, local-only enforcement
  and per-question fallback. `decision/provider.py` adapts JSON requests to the
  agent transport; decision agents do not generate prose or call tools.
- `decision/gateways/`: Laya HTTP and TypeSafe Jev clients. Laya owns its internal
  rules; its gateway-file strategy is read on each call without restart.
- `llm_config.py`, `llm_options.py`, `token_limits.py`, `model_tiers.py`,
  `reasoning_effort.py`, `cooldown.py`, `gateway_failover.py`, `cancellation.py`
  and `context_breakdown.py`: shared provider configuration and runtime policy.

Agent definitions, roles and prompts are under `../agents/`; brokers, trusted
identity, history, configuration and usage recording are under `../runtime/`.
