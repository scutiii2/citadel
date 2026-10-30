"""What fills a turn's context window, part by part, for the chat's context panel.

The last round's prompt is split into the system prompt, the delegable-agent
list, the built-in tools (delegate, ask the user, checklist), the MCP tools
and the messages. Providers only report the whole prompt's size, so the static
parts are counted here and the messages get the remainder: the parts always add
up to the provider's own `context_tokens`.

Two ways to count a static part. `EstimateCounter` (about four characters a
token) is free and always works. `ProviderCounter` asks the provider's own
token-count endpoint, for a turn that asked for exact counts (`bind_exact`);
results are cached, so only the first turn after a change to the prompt, the
tools or the model makes requests. Any failure falls back to the estimate, so
counting can never fail a turn.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import logging
import math
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence

from src.agents.roles.orchestrator import ask_user, delegation, plan

logger = logging.getLogger(__name__)


class TokenCounter(Protocol):
    """Counts the tokens of one piece of prompt text."""

    def count(self, text: str) -> int: ...


class EstimateCounter:
    """About four characters a token, the same rule as token_limits.estimate_context_tokens."""

    def count(self, text: str) -> int:
        return math.ceil(len(text) / 4) if text else 0


class RequestCounter(Protocol):
    """Asks a provider how many input tokens a minimal request has: one short
    user message plus the given system text and tool definitions."""

    async def count(self, *, system: str = "", tools: Sequence[Mapping[str, Any]] = ()) -> int: ...


_BUILTIN_TOOLS = frozenset({delegation.TOOL_NAME, ask_user.TOOL_NAME, plan.TOOL_NAME, "submit_plan"})

SYSTEM_PROMPT = "system_prompt"
AGENTS = "agents"
BUILTIN_TOOLS = "builtin_tools"
MCP_TOOLS = "mcp_tools"
MESSAGES = "messages"

_LABELS = {
    SYSTEM_PROMPT: "System prompt",
    AGENTS: "Delegable agents",
    BUILTIN_TOOLS: "Built-in tools",
    MCP_TOOLS: "MCP tools",
    MESSAGES: "Messages",
}

# The longest the exact counting may take before the turn settles for the estimate.
EXACT_TIMEOUT_SECONDS = 3.0

_exact: contextvars.ContextVar[bool] = contextvars.ContextVar("exact_context", default=False)


def bind_exact(on: bool) -> contextvars.Token[bool]:
    """Marks this turn as one that wants exact counts."""
    return _exact.set(on)


def reset_exact(token: contextvars.Token[bool]) -> None:
    _exact.reset(token)


def exact_requested() -> bool:
    return _exact.get()


def _schema_text(schema: Mapping[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, default=str, separators=(",", ":"))


def _split_schemas(schemas: Sequence[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """(built-in tools, MCP tools)."""
    builtin = [s for s in schemas if s.get("name") in _BUILTIN_TOOLS]
    return builtin, [s for s in schemas if s.get("name") not in _BUILTIN_TOOLS]


def _assemble(context_tokens: int | None, static: Mapping[str, int]) -> list[dict[str, Any]]:
    """Parts from the counted static ones: "messages" takes whatever they leave of
    `context_tokens`. If the static parts alone count more, they are scaled down to
    fit. Parts with no tokens are left out; a provider that did not report a size
    gives an empty list."""
    if not context_tokens or context_tokens <= 0:
        return []
    parts = dict(static)
    total = sum(parts.values())
    if total > context_tokens:
        parts = {key: tokens * context_tokens // total for key, tokens in parts.items()}
        total = sum(parts.values())
    parts[MESSAGES] = context_tokens - total
    return [{"id": key, "label": _LABELS[key], "tokens": tokens} for key, tokens in parts.items() if tokens > 0]


def build_breakdown(
    context_tokens: int | None,
    system_prompt: str,
    roster_text: str,
    schemas: Sequence[Mapping[str, Any]],
    counter: TokenCounter | None = None,
) -> list[dict[str, Any]]:
    """The parts of a prompt of `context_tokens` tokens, as [{id, label, tokens}],
    counted with `counter` (the estimate by default).

    `roster_text` is the part of `system_prompt` that lists the delegable agents.
    `schemas` are the tool definitions as sent, each with a "name"."""
    counter = counter or EstimateCounter()
    builtin, mcp = _split_schemas(schemas)
    agents = counter.count(roster_text)
    return _assemble(context_tokens, {
        SYSTEM_PROMPT: max(0, counter.count(system_prompt) - agents),
        AGENTS: agents,
        BUILTIN_TOOLS: sum(counter.count(_schema_text(s)) for s in builtin),
        MCP_TOOLS: sum(counter.count(_schema_text(s)) for s in mcp),
    })


class ProviderCounter:
    """Counts the static parts of a prompt with a provider's own endpoint.

    Each part is counted as a minimal request that carries only that part, less
    the same request with nothing in it (the baseline: the one short message the
    endpoint needs). Counts are cached by model and content, so a part that did
    not change costs nothing the next turn."""

    _cache: dict[tuple[str, str, str], int] = {}

    def __init__(self, client: RequestCounter, model: str) -> None:
        self._client = client
        self._model = model

    async def _cached(self, kind: str, content: str, count: Callable[[], Awaitable[int]]) -> int:
        key = (self._model, kind, hashlib.sha256(content.encode("utf-8")).hexdigest())
        if key not in self._cache:
            self._cache[key] = await count()
        return self._cache[key]

    async def _baseline(self) -> int:
        return await self._cached("baseline", "", lambda: self._client.count())

    async def _system(self, text: str, baseline: int) -> int:
        if not text:
            return 0
        counted = await self._cached("system", text, lambda: self._client.count(system=text))
        return max(0, counted - baseline)

    async def _tools(self, schemas: Sequence[Mapping[str, Any]], baseline: int) -> int:
        if not schemas:
            return 0
        text = "[" + ",".join(_schema_text(s) for s in schemas) + "]"
        counted = await self._cached("tools", text, lambda: self._client.count(tools=list(schemas)))
        return max(0, counted - baseline)

    async def static_parts(
        self, system_prompt: str, roster_text: str, schemas: Sequence[Mapping[str, Any]]
    ) -> dict[str, int]:
        builtin, mcp = _split_schemas(schemas)
        without_roster = system_prompt.replace(roster_text, "") if roster_text else system_prompt
        baseline = await self._baseline()
        system, agents, builtin_tokens, mcp_tokens = await asyncio.gather(
            self._system(without_roster, baseline), self._system(roster_text, baseline),
            self._tools(builtin, baseline), self._tools(mcp, baseline),
        )
        return {SYSTEM_PROMPT: system, AGENTS: agents, BUILTIN_TOOLS: builtin_tokens, MCP_TOOLS: mcp_tokens}


async def breakdown_fields(
    context_tokens: int | None,
    system_prompt: str,
    roster_text: str,
    schemas: Sequence[Mapping[str, Any]],
    counter: Callable[[], ProviderCounter | None] | None = None,
) -> dict[str, Any]:
    """The ChatResult fields for a finished turn: `context_breakdown` and
    `context_breakdown_exact`.

    When this turn asked for exact counts and `counter` makes a provider
    counter, the parts are counted with it; if that fails or takes longer than
    EXACT_TIMEOUT_SECONDS the estimate is used and `context_breakdown_exact`
    stays False."""
    if exact_requested() and counter is not None and context_tokens:
        try:
            provider_counter = counter()
            if provider_counter is not None:
                static = await asyncio.wait_for(
                    provider_counter.static_parts(system_prompt, roster_text, schemas), EXACT_TIMEOUT_SECONDS
                )
                return {"context_breakdown": _assemble(context_tokens, static), "context_breakdown_exact": True}
        except Exception as error:  # noqa: BLE001 - any failure just means "estimate instead"
            logger.warning("exact context counting failed, using the estimate: %s", error)
    return {
        "context_breakdown": build_breakdown(context_tokens, system_prompt, roster_text, schemas),
        "context_breakdown_exact": False,
    }
