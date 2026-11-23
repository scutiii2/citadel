"""Providers. A new provider is one adapter file plus one line in PROVIDERS."""
from __future__ import annotations

from typing import Any

import httpx

from importlib import import_module

from src.gateway.conversation.gateways.base import BaseGateway

# provider -> (module, class). Adapters load on first use: the Anthropic and OpenAI SDKs take seconds to import, and
# an agent that never calls a gateway of that provider should not pay for them at start.
PROVIDERS: dict[str, tuple[str, str]] = {
    "anthropic": ("anthropic", "AnthropicGateway"),
    "openai": ("openai", "OpenAIGateway"),
    "scuti": ("scuti", "ScutiGateway"),
}


def build_gateway(gateway_id: str, entry: dict[str, Any], transport: httpx.AsyncBaseTransport | None = None) -> BaseGateway:
    module, name = PROVIDERS[entry["provider"]]
    adapter: type[BaseGateway] = getattr(import_module(f"src.gateway.conversation.gateways.{module}"), name)
    return adapter(gateway_id, entry, transport)
