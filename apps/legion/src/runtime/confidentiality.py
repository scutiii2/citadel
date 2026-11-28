"""Does a request hold secret data? If so the turn is confidential, and only trusted gateways may see it.

The Confidentiality Checker is a decision agent (agents/confidentiality-checker.json) that asks Jev alone. A
turn starts not confidential; `mark()` sets it for the rest of the turn, delegated agents included (`ask`
carries `confidential`). Every part of a text is read; one too long to read counts as confidential. The check
fails closed: a checker that is missing, disabled, unreachable, slow or unsure counts as confidential, so the
text goes only to a trusted gateway.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import OrderedDict
from collections.abc import Sequence
from contextvars import ContextVar, Token

import anyio

from src.agents import agent_registry, agent_spec
from src.providers import gateway_client
from src.providers.gateway_failover import GatewayRoute, NoTrustedGateway, SwitchInfo
from src.runtime import counters

AGENT_ID = "confidentiality-checker"
TIMEOUT_SECONDS = 8
PIECE_CHARS = 4000  # what the checker reads at once
OVERLAP_CHARS = 200  # so a secret on a boundary is whole in one piece
MAX_CHARS = 100_000  # a longer text is not read: it counts as confidential
PARALLEL = 4
MAX_REMEMBERED = 4096

_confidential: ContextVar[bool] = ContextVar("confidential_turn", default=False)
# Digests of pieces found public (never the text), oldest first, so a long chat is not read again every turn.
_public: OrderedDict[bytes, None] = OrderedDict()

CHOICES = {
    "confidential": (
        "The text holds secret data: a password, API key, token, private key or other credential; a personal "
        "identifier (ID, passport, tax or social security number); a bank account or card number; health details "
        "about a person; or anything the user calls private or secret."),
    "public": (
        "The text holds none of those: general questions, public facts, ordinary writing, notes, emails, documents, "
        "business, legal or money matters without such numbers, code that contains no secret, and tool output "
        "without such data."),
}
QUESTION = "Does the text contain secret data?"


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


def _pieces(text: str) -> list[str]:
    starts = range(0, max(len(text) - OVERLAP_CHARS, 1), PIECE_CHARS - OVERLAP_CHARS)
    return [piece for start in starts if (piece := text[start:start + PIECE_CHARS]).strip()]


def _digest(piece: str) -> bytes:
    return hashlib.sha256(piece.encode("utf-8", "surrogatepass")).digest()


def _remember(digest: bytes) -> None:
    _public[digest] = None
    while len(_public) > MAX_REMEMBERED:
        _public.popitem(last=False)


async def _checker_url() -> str | None:
    try:
        with anyio.fail_after(TIMEOUT_SECONDS):
            await anyio.to_thread.run_sync(agent_registry.reload, abandon_on_cancel=True)
        agent = agent_registry.get_agent(AGENT_ID)
        return None if agent is None else agent["url"]
    except Exception:
        counters.add("confidential.failed_closed")
        return None


async def _ask_checker(url: str, piece: str) -> bool:
    """True when `piece` holds secret data or the checker cannot tell."""
    from src.agents.roles.orchestrator import delegation  # delegation imports this module

    try:
        with anyio.fail_after(TIMEOUT_SECONDS):
            request = {"text": piece, "questions": {"verdict": {
                "type": "choice", "instructions": QUESTION, "criteria": CHOICES}}}
            result = await delegation._call_tool(url, "ask", {
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


async def is_confidential(*texts: str) -> bool:
    """True when any of `texts` holds secret data or the checker cannot tell. A part already found public is not
    asked about again."""
    if any(len(text) > MAX_CHARS for text in texts):
        return True
    pending = {digest: piece for text in texts for piece in _pieces(text) if (digest := _digest(piece)) not in _public}
    if not pending:
        return False
    url = await _checker_url()
    if url is None:
        return True
    found = False
    limit = anyio.CapacityLimiter(PARALLEL)

    async def check(digest: bytes, piece: str) -> None:
        nonlocal found
        async with limit:
            if found:  # one secret part settles it
                return
            if await _ask_checker(url, piece):
                found = True
            else:
                _remember(digest)

    async with anyio.create_task_group() as tasks:
        for digest, piece in pending.items():
            tasks.start_soon(check, digest, piece)
    return found


def _untrusted_decision_gateway() -> bool:
    """Whether a decision gateway this agent asks (its own list, or the Router's for the orchestrator) is not
    trusted."""
    from src.providers.decision import gateway_client as decision_client, router_list

    spec = agent_spec.current()
    if spec.llm.provider == "decision":
        names = spec.llm.gateway_names
    else:
        names = router_list.router_models() if spec.orchestrator else ()
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


async def protect_turn(text: str, reason: str = "check", earlier: Sequence[str] = ()) -> None:
    """Before text reaches a model: mark the turn confidential when `text`, or one of the `earlier` messages sent
    with it, is. Skipped (no Jev call) when the turn already is, or when this agent has no untrusted gateway."""
    if not _confidential.get() and has_untrusted_gateway() and await is_confidential(*earlier, text):
        mark(reason)


def route_for_turn(route: GatewayRoute) -> GatewayRoute:
    """`route`, moved to a trusted gateway when the turn is confidential. Raises NoTrustedGateway when none can take it."""
    if _confidential.get():
        _require(route)
    return route


async def protect_round(route: GatewayRoute, results: list[str]) -> SwitchInfo | None:
    """After a round of tool calls, before the model sees the results: when they are confidential, the rest of the
    turn goes only to trusted gateways. Returns the switch, if the route had to move."""
    if route.trusted_only is None and not _confidential.get():
        if not any(not gateway_client.is_trusted(name) for name in route.candidates):
            return None
        if not await is_confidential(*results):
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
