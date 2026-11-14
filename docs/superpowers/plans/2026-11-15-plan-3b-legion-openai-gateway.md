# Plan 3b: Legion on ConversationGateway, OpenAI-protocol agents

Branch: `refactor/legion-openai-gateway`. Follows Plan 3; same approach ("swap the client, keep the loop").

## Goal

`openai_provider.py` calls its models through ConversationGateway. The OpenAI SDK and every provider key leave Legion.

## Tasks

1. `src/providers/language/openai_gateway_shim.py`: translate Responses-API requests (`input`, `tools`, `max_output_tokens`, `temperature`, `reasoning`) to the gateway chat body, and gateway replies to a Responses-shaped object (`output`, `output_text`, `usage`). Tests in `tests/test_openai_gateway_shim.py`.
2. `openai_provider.py`: `get_client`/`get_sync_client` return the shim; `has_api_key` means "saved in ConversationGateway"; a 422 without a kind drives `drop_rejected`.
3. `gateway_failover.classify()`: only `GatewayCallError`. Remove the `openai` dependency.
4. `gateways/openai/*.json`: keep `label`, `prompt_cache`, `model`, `models`.
5. Rewrite the tests that built SDK errors; run the whole Legion suite.
6. Docs and vault notes.

## Accepted behavior changes

1. One model round arrives as one assistant message at the gateway (reasoning state, text, tool calls), and its tool outputs as one `tool` message.
2. Mid-stream provider failures (`response.failed`) are no longer mapped in Legion. The gateway reports them as an error line with a kind; `gateway_client` raises `GatewayCallError`.
3. The context breakdown is always an estimate: the gateway has no token-count route.
4. The gateway picks the wire protocol (Responses, Chat Completions, Azure) per saved gateway. Legion no longer cares which one a vendor supports.
5. Azure deployment names stay as `{AZURE_OPENAI_DEPLOYMENT_*}` placeholders for model ids; endpoint, API version and key are saved in ConversationGateway.

## Execution notes (2026-11-15)

- Executed in full. Legion suite: 1460 passed (1463 before; 12 shim tests and 2 provider tests added, 17 SDK-only tests removed or merged: SDK status classification (10), SDK transport errors (2), HTTP-200 "overloaded" (1), `response.failed` mapping (3), env-var key check (1)).
- Not run: Docker build, any live call through ConversationGateway.
- `.env.example` no longer lists provider keys for either protocol.
