"""Providers. A new provider is one adapter file plus one line in PROVIDERS."""
from __future__ import annotations

from typing import Any

import httpx

from src.gateway.conversation.gateways.base import BaseGateway

from src.gateway.conversation.gateways.anthropic import AnthropicGateway
from src.gateway.conversation.gateways.openai import OpenAIGateway
from src.gateway.conversation.gateways.scuti import ScutiGateway

PROVIDERS: dict[str, type[BaseGateway]] = {"anthropic": AnthropicGateway, "openai": OpenAIGateway, "scuti": ScutiGateway}


def build_gateway(gateway_id: str, entry: dict[str, Any], transport: httpx.AsyncBaseTransport | None = None) -> BaseGateway:
    return PROVIDERS[entry["provider"]](gateway_id, entry, transport)
