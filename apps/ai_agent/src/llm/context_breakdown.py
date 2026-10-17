"""What fills a turn's context window, part by part, for the chat's context panel.

The last round's prompt is split into the system prompt, the delegable-agent
list, the built-in tools (delegate, ask the user, checklist), the MCP tools
and the messages. Providers only report the whole prompt's size, so the static
parts are counted here and the messages get the remainder: the parts always add
up to the provider's own `context_tokens`. How a part is counted is a
`TokenCounter`; `EstimateCounter` (about four characters a token) is the free
one, and an exact counter can replace it without touching the callers.
"""

from __future__ import annotations

import json
import math
from typing import Any, Mapping, Protocol, Sequence

from src.agents import ask_user, delegation, plan


class TokenCounter(Protocol):
    """Counts the tokens of one piece of prompt text."""

    def count(self, text: str) -> int: ...


class EstimateCounter:
    """About four characters a token, the same rule as token_limits.estimate_context_tokens."""

    def count(self, text: str) -> int:
        return math.ceil(len(text) / 4) if text else 0


_BUILTIN_TOOLS = frozenset({delegation.TOOL_NAME, ask_user.TOOL_NAME, plan.TOOL_NAME})

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


def _schema_text(schema: Mapping[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, default=str, separators=(",", ":"))


def build_breakdown(
    context_tokens: int | None,
    system_prompt: str,
    roster_text: str,
    schemas: Sequence[Mapping[str, Any]],
    counter: TokenCounter | None = None,
) -> list[dict[str, Any]]:
    """The parts of a prompt of `context_tokens` tokens, as [{id, label, tokens}].

    `roster_text` is the part of `system_prompt` that lists the delegable agents.
    `schemas` are the tool definitions as sent, each with a "name". Parts with
    no tokens are left out; "messages" is always last and takes whatever the
    other parts leave of `context_tokens`. If the static parts alone count more
    than `context_tokens` they are scaled down to fit. A provider that did not
    report a size gives an empty list."""
    if not context_tokens or context_tokens <= 0:
        return []
    counter = counter or EstimateCounter()
    agents = counter.count(roster_text)
    parts = {
        SYSTEM_PROMPT: max(0, counter.count(system_prompt) - agents),
        AGENTS: agents,
        BUILTIN_TOOLS: sum(counter.count(_schema_text(s)) for s in schemas if s.get("name") in _BUILTIN_TOOLS),
        MCP_TOOLS: sum(counter.count(_schema_text(s)) for s in schemas if s.get("name") not in _BUILTIN_TOOLS),
    }
    static = sum(parts.values())
    if static > context_tokens:
        parts = {key: tokens * context_tokens // static for key, tokens in parts.items()}
        static = sum(parts.values())
    parts[MESSAGES] = context_tokens - static
    return [{"id": key, "label": _LABELS[key], "tokens": tokens} for key, tokens in parts.items() if tokens > 0]
