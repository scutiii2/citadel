"""Which protocol each of an agent's gateways speaks, and the agent's gateways in order per protocol.

An agent's list is its primary gateway, then `llm.fallback_gateways`. The list may mix protocols (anthropic and
openai): each provider module runs only the gateways of its own protocol, and `agent_config.run_chat` moves a turn to
the next protocol when one has none left. A gateway's protocol is the `provider` of its saved entry, else the
provider folder of its template file; a name found nowhere is taken to speak the agent's own protocol.
"""

from __future__ import annotations

import os

from src.agents import agent_spec
from src.providers import llm_config

CHAT_PROTOCOLS = ("anthropic", "openai")


def protocol_of(name: str, own: str) -> str:
    """The protocol of gateway `name`; `own` (the agent's protocol) when it is saved nowhere or is ambiguous."""
    from src import gateway

    try:
        saved = gateway.chat_store().all().get(name)
    except Exception:  # Legion starts before gateways exist; the template files still answer
        saved = None
    if isinstance(saved, dict) and saved.get("provider") in CHAT_PROTOCOLS:
        return saved["provider"]
    try:
        blocks = llm_config.load_gateways()
    except (OSError, ValueError):
        return own
    if name in (blocks.get(own) or {}):
        return own
    return next((provider for provider in CHAT_PROTOCOLS if name in (blocks.get(provider) or {})), own)


def _names() -> tuple[str, list[str]]:
    spec = agent_spec.current()
    own = spec.llm.provider
    primary = os.getenv("AI_AGENT_GATEWAY") or agent_spec.default_gateway(own)
    return own, list(dict.fromkeys([primary, *(choice.gateway for choice in spec.llm.fallback_gateways)]))


def order(provider: str) -> tuple[str, ...]:
    """This agent's gateways that speak `provider`, in the order they are tried."""
    own, names = _names()
    if len(names) == 1:
        return tuple(names) if provider == own else ()
    return tuple(name for name in names if protocol_of(name, own) == provider)


def protocols() -> tuple[str, ...]:
    """The protocols this agent's gateways speak, in the order of their first gateway."""
    own, names = _names()
    if len(names) == 1:
        return (own,)
    return tuple(dict.fromkeys(protocol_of(name, own) for name in names))


def explicit_model(name: str) -> str | None:
    """The model a fallback entry pins for gateway `name`, if any."""
    return next((choice.model for choice in agent_spec.current().llm.fallback_gateways if choice.gateway == name), None)
