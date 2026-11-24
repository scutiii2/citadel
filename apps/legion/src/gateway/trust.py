"""Which model gateways may see confidential data.

A gateway is trusted when its entry says `trusted: true`. An entry that does not say defaults by what the
gateway is: the hosted models the owner picked (Claude, GPT, Gemini, Jev), and every gateway that runs on
the owner's own machine (Ollama, a Scuti model service, Laya). Anything else, such as a router over free
tiers, starts untrusted until an admin marks it on the gateway's setup.
"""

from __future__ import annotations

from typing import Any

CONVERSATION_DEFAULTS = frozenset({"claude", "gpt", "gemini", "ollama"})
DECISION_DEFAULTS = frozenset({"jev", "laya"})
DECISION_LOCAL_KINDS = frozenset({"ollama", "scuti"})


def conversation(gateway_id: str, entry: dict[str, Any] | None = None) -> bool:
    entry = entry or {}
    if isinstance(entry.get("trusted"), bool):
        return entry["trusted"]
    return gateway_id in CONVERSATION_DEFAULTS or entry.get("provider") == "scuti"


def decision(gateway_id: str, entry: dict[str, Any] | None = None) -> bool:
    entry = entry or {}
    if isinstance(entry.get("trusted"), bool):
        return entry["trusted"]
    return gateway_id in DECISION_DEFAULTS or entry.get("kind") in DECISION_LOCAL_KINDS


def clean(data: dict[str, Any], old: dict[str, Any]) -> bool | None:
    """The `trusted` value to store: a bool the admin sent (or kept), else None, which leaves the default."""
    value = data.get("trusted", old.get("trusted"))
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("trusted must be true or false.")
    return value
