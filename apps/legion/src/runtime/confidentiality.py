"""Does a request hold confidential data? If so, only trusted gateways may see it.

The Confidentiality Checker is a decision agent (agents/confidentiality-checker.json) that asks Jev alone. A
turn starts not confidential; `mark()` sets it for the rest of the turn, delegated agents included (`ask`
carries `confidential`). The check fails closed: a checker that is missing, disabled, unreachable, slow or unsure
counts as confidential, so the text goes only to a trusted gateway.
"""

from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar, Token

import anyio

from src.agents import agent_registry, agent_spec
from src.providers import gateway_client
from src.providers.gateway_failover import GatewayRoute, NoTrustedGateway, SwitchInfo
from src.runtime import counters

AGENT_ID = "confidentiality-checker"
TIMEOUT_SECONDS = 8
MAX_CHARS = 4000  # what the checker reads; a longer text is checked by its start and its end

_confidential: ContextVar[bool] = ContextVar("confidential_turn", default=False)

CHOICES = {
    "confidential": (
        "The text holds confidential data: a password, API key, token or other credential; a personal identifier "
        "(ID, passport or tax number); a bank or card number; health, legal or financial details about a person; "
        "the private messages, email or documents of the user or someone else; unreleased business or source-code "
        "material; or anything the user calls private or secret."),
    "public": (
        "The text holds nothing confidential: general questions, public facts, ordinary writing or code that "
        "contains no secret, and tool output about public things."),
}
QUESTION = "Does the text contain confidential data?"


def current() -> bool:
    return _confidential.get()


def bind(on: bool) -> Token:
    return _confidential.set(on)


def reset(token: Token) -> None:
    _confidential.reset(token)


def mark(reason: str = "check") -> None:
    """The rest of this turn, and every agent it delegates to, is confidential. `reason` is only counted."""
    _confidential.set(True)
    counters.add(f"confidential.marked.{reason}")


def _excerpt(text: str) -> str:
    if len(text) <= MAX_CHARS:
        return text
    half = MAX_CHARS // 2
    return text[:half] + "\n[middle omitted]\n" + text[-half:]


async def is_confidential(text: str, request_id: str | None = None) -> bool:
    """True when `text` holds confidential data or the checker cannot tell."""
    if not text.strip():
        return False
    from src.agents.roles.orchestrator import delegation  # delegation imports this module

    try:
        with anyio.fail_after(TIMEOUT_SECONDS):
            await anyio.to_thread.run_sync(agent_registry.reload, abandon_on_cancel=True)
            agent = agent_registry.get_agent(AGENT_ID)
            if agent is None:
                return True
            request = {"text": _excerpt(text), "questions": {"verdict": {
                "type": "choice", "instructions": QUESTION, "criteria": CHOICES}}}
            result = await delegation._call_tool(agent["url"], "ask", {
                "question": json.dumps(request), "history": [], "request_id": None, "depth": 1,
                "delegated_by": agent_spec.current().id,
            })
        verdict = json.loads(result["response"])["answers"]["verdict"]
        counters.add("confidential.checks")
        unsure = bool(verdict.get("uncertain"))
        if unsure:
            counters.add("confidential.unsure")
        return verdict["choice"] != "public" or unsure
    except Exception:
        # Never log the text or a provider error: both may carry the data being checked.
        counters.add("confidential.failed_closed")
        return True


def _untrusted_decision_gateway() -> bool:
    """Whether a decision gateway this agent asks (as the Router's helper, or as a decision agent) is not trusted."""
    from src.providers.decision import gateway_client as decision_client, strategy

    spec = agent_spec.current()
    if spec.llm.provider == "decision":
        names = strategy._ORDER.get(spec.llm.strategy or "both", ())
    else:
        names = strategy._ORDER["both"] if spec.orchestrator else ()
    return any(not decision_client.is_trusted(name) for name in names)


def has_untrusted_gateway() -> bool:
    """Whether this agent could send a request to a gateway that is not trusted: a chat gateway, or a decision one."""
    llm = agent_spec.current().llm
    if llm.provider == "decision":
        return agent_spec.current().id != AGENT_ID and _untrusted_decision_gateway()
    if _untrusted_decision_gateway():
        return True
    names = [llm.gateway or agent_spec.default_gateway(llm.provider), *(choice.gateway for choice in llm.fallback_gateways)]
    return any(name is not None and not gateway_client.is_trusted(name) for name in names)


async def protect_turn(text: str, request_id: str | None = None) -> None:
    """At the start of a top-level turn: mark it confidential when `text` is. Skipped (no Jev call) when the turn
    already is, or when this agent has no untrusted gateway to protect from."""
    if not _confidential.get() and has_untrusted_gateway() and await is_confidential(text, request_id):
        mark()


def route_for_turn(route: GatewayRoute) -> GatewayRoute:
    """`route`, moved to a trusted gateway when the turn is confidential. Raises NoTrustedGateway when none can take it."""
    if _confidential.get():
        _require(route)
    return route


async def protect_round(route: GatewayRoute, results: list[str], request_id: str | None = None) -> SwitchInfo | None:
    """After a round of tool calls, before the model sees the results: when they are confidential, the rest of the
    turn goes only to trusted gateways. Returns the switch, if the route had to move."""
    if route.trusted_only is None and not _confidential.get():
        if not any(not gateway_client.is_trusted(name) for name in route.candidates):
            return None
        if not await is_confidential("\n\n".join(results), request_id):
            return None
        mark("tool_result")
    return _require(route)


def protect_text_sync(text: str) -> None:
    """`protect_turn` for a worker thread (the single-completion `interpret` path). Inside a running event loop the
    turn's own check already ran, so this does nothing there."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(protect_turn(text))


def _require(route: GatewayRoute) -> SwitchInfo | None:
    try:
        switch = route.require_trusted(gateway_client.is_trusted)
    except NoTrustedGateway:
        counters.add("confidential.refused")
        raise
    if switch:
        counters.add("confidential.switches")
    return switch
