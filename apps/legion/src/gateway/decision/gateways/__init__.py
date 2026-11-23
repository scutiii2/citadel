"""Gateway kinds. A new kind is one adapter file plus one line in KINDS."""
from __future__ import annotations

from typing import Any

import httpx

from src.gateway.decision.gateways.base import BaseGateway
from src.gateway.decision.gateways.typesafe import TypeSafeGateway
from src.gateway.decision.gateways.ollama import OllamaGateway
from src.gateway.decision.gateways.freellmapi import FreeLLMAPIGateway
from src.gateway.decision.gateways.scuti import ScutiGateway

KINDS: dict[str, type[BaseGateway]] = {"typesafe": TypeSafeGateway, "ollama": OllamaGateway, "scuti": ScutiGateway,
                                       "freellmapi": FreeLLMAPIGateway}


def build_gateway(gateway_id: str, entry: dict[str, Any], transport: httpx.AsyncBaseTransport | None = None) -> BaseGateway:
    return KINDS[entry["kind"]](gateway_id, entry, transport)
