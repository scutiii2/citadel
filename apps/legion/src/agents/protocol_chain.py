"""Failover between protocols: an agent whose gateways speak both anthropic and openai runs a turn on the first
protocol that can take it, and moves the whole turn to the next one when the first has no gateway left.

Inside a provider module the tool loop stays in that protocol's own message shape, so a turn is never converted
midway. It is run again from the start, with the same question and history, and only while it has done nothing that
cannot safely be repeated (`turn_effects`). A single-protocol agent never reaches this code.
"""

from __future__ import annotations

import importlib
from typing import Any

from src.providers import cooldown, gateway_client, gateway_protocols, model_tiers
from src.providers.gateway_failover import NoTrustedGateway, SwitchInfo, classify
from src.runtime import confidentiality, counters, turn_effects

MODULES = {
    "anthropic": "src.providers.language.anthropic_provider",
    "openai": "src.providers.language.openai_provider",
}


def module_for(protocol: str) -> Any:
    return importlib.import_module(MODULES[protocol])


def protocols_for(own: str) -> tuple[str, ...]:
    """The protocols to try, in order; a decision agent has gateways of no protocol."""
    return (own,) if own == "decision" else gateway_protocols.protocols()


def usable(protocol: str) -> bool:
    """Whether some gateway of `protocol` could take the turn now: saved, not cooling down, and trusted when the turn is confidential."""
    secret = confidentiality.current()
    return any(gateway_client.is_saved(name)
               and not cooldown.is_in_cooldown(cooldown.gateway_key(protocol, name))
               and (not secret or gateway_client.is_trusted(name))
               for name in gateway_protocols.order(protocol))


def first(protocols: tuple[str, ...]) -> int:
    """Where to start: the first protocol with a usable gateway, else the first one (it reports the failure)."""
    return next((index for index, protocol in enumerate(protocols) if usable(protocol)), 0)


def can_move_on(error: Exception) -> bool:
    """A protocol is used up (every gateway failed in a way failover handles, or none is trusted) and nothing was done."""
    return (isinstance(error, NoTrustedGateway) or classify(error) is not None) and not turn_effects.happened()


def model_for(protocol: str, tier: str | None, min_tier: str | None, max_tier: str | None, agent_id: str) -> str | None:
    """The model for the first gateway of `protocol`: its pinned model, else the tier asked for, else its default (None)."""
    names = gateway_protocols.order(protocol)
    if not names:
        return None
    pinned = gateway_protocols.explicit_model(names[0])
    if pinned or not tier:
        return pinned
    return model_tiers.resolve(tier, model_tiers.effective_tiers(protocol, names[0], min_tier, max_tier), None, agent_id).model


async def announce(on_event: Any, old: str, new: str) -> SwitchInfo:
    """Clear the text already streamed and tell the client the turn moved protocols."""
    from src.providers.base_provider import step_event

    switch = SwitchInfo(gateway_protocols.order(old)[0] if gateway_protocols.order(old) else old,
                        gateway_protocols.order(new)[0], "protocol")
    counters.add("failover.protocol_switch")
    if on_event:
        await on_event(step_event("token_reset"))
        await on_event(step_event("gateway_switch", **switch.as_dict()))
    return switch
