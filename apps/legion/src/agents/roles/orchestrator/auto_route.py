"""Send a question straight to a specialist, without the orchestrator's own model call.

When config_tuning.json's `classifier.auto_route.enabled` is on and a backend of the
auto_route chain is available (llm/decision.py), an orchestrator's top-level turn first asks the
classifier which specialist, if any, fits the question. A confident pick is handed
to that specialist exactly as a `delegate_to_agent` call would be (same events,
same usage rows) and its answer becomes the turn's answer, so the orchestrator's
model never runs. No pick means the orchestrator answers as usual.

Only specialists with tools of their own are offered (a tool-less one such as the
reviewer is a helper the orchestrator chooses itself), and only when the turn needs
no approval to delegate: with "ask" the orchestrator asks the user the usual way.
A specialist that fails is reported, not retried: it may already have acted.
The text sent to the classifier is the question and the last assistant message
(clipped); a remote backend sends it off this machine and bills each call.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import anyio.to_thread

from src.agents import agent_routing
from src.agents.roles.orchestrator import delegation
from src.agents.agent_spec import RosterEntry
from src.runtime import approvals
from src.providers import cancellation
from src.providers.decision import settings, strategy
from src.providers.decision.contract import DecisionError
from src.providers.base_provider import ChatCancelled, ChatResult, OnEvent, ToolCallRecord, dispatch_with_progress, step_event

_log = logging.getLogger(__name__)

NONE = "none"
QUESTION = "Which specialist should handle the user's latest message?"
_FOCUS_CHARS = 160
# What the classifier sees of the assistant's last message: its end, where a follow-up points.
_CLASSIFIER_CONTEXT_CHARS = 300
# What the specialist gets of it, since a specialist never sees the chat.
_HANDOFF_CONTEXT_CHARS = 600


@dataclass(frozen=True)
class Route:
    entry: RosterEntry
    confidence: int
    prompt_tokens: int
    backend: str
    model: str


def enabled() -> bool:
    return settings.settings().auto_route.enabled and settings.available("auto_route")


def routable(roster: list[RosterEntry]) -> list[RosterEntry]:
    """The specialists a question may be sent to: those with tools of their own."""
    return [entry for entry in roster if agent_routing.own_tools(entry)]


def _last_assistant(history: list[dict[str, Any]]) -> str:
    for message in reversed(history):
        if isinstance(message, dict) and message.get("role") == "assistant" and isinstance(message.get("content"), str):
            return message["content"].strip()
    return ""


def _subject(question: str, history: list[dict[str, Any]], cap: int) -> str:
    lines = []
    previous = _last_assistant(history)
    if previous:
        lines.append(f"Previous assistant message: {previous[-_CLASSIFIER_CONTEXT_CHARS:]}")
    lines.append(f"User message: {question[:cap]}")
    return "\n".join(lines)


def _handoff(question: str, history: list[dict[str, Any]]) -> str:
    previous = _last_assistant(history)
    if not previous:
        return question
    return f"Context, the assistant's previous message: {previous[-_HANDOFF_CONTEXT_CHARS:]}\n\nUser message: {question}"


async def pick(question: str, history: list[dict[str, Any]], roster: list[RosterEntry]) -> Route | None:
    """The specialist `question` belongs to, or None to let the orchestrator answer."""
    candidates = routable(roster)
    text = question.strip()
    if not candidates or not text:
        return None
    config = settings.settings()
    criteria = {entry.id: (entry.focus or entry.label)[:_FOCUS_CHARS] for entry in candidates}
    criteria[NONE] = "no specialist is needed: a general assistant should answer"
    try:
        picked = await anyio.to_thread.run_sync(
            lambda: strategy.ask_choice(
                _subject(text, history, config.max_input_chars), criteria, QUESTION, strategy=config.auto_route.strategy,
                min_confidence=config.auto_route.min_confidence, timeout=config.timeout_seconds,
            )
        )
    except DecisionError as error:
        _log.warning("auto route skipped: %s", error)
        return None
    if picked.choice == NONE or picked.confidence < config.auto_route.min_confidence:
        return None
    entry = next((e for e in candidates if e.id == picked.choice), None)
    return Route(entry, picked.confidence, picked.prompt_tokens, picked.backend, picked.model) if entry else None


async def try_route(
    question: str, history: list[dict[str, Any]], on_event: OnEvent | None, request_id: str | None, depth: int,
) -> ChatResult | None:
    """The turn's result when a specialist answered it, else None (the orchestrator runs as usual)."""
    if depth != 0 or not enabled():
        return None
    if approvals.current().needs_approval(delegation.TOOL_NAME):
        return None  # the user would have to approve the delegation; the orchestrator asks the usual way
    route = await pick(question, history, await agent_routing.roster_for())
    if route is None:
        return None
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()
    label = route.entry.label
    arguments = {"agent_id": route.entry.id, "question": _handoff(question, history)}
    step_id = f"route-{uuid.uuid4().hex[:8]}"
    if on_event:
        await on_event(step_event("step_start", id=step_id, tool=delegation.TOOL_NAME, label=f"Asking {label}", arguments=arguments))
    try:
        text = await dispatch_with_progress(delegation.dispatch, on_event, step_id, arguments, depth)
        ok = True
    except Exception as error:  # noqa: BLE001 - reported to the user; a retry could repeat what the specialist did
        text = f"I sent this to {label}, but it could not finish: {error}"
        ok = False
    if on_event:
        await on_event(step_event("step_end", id=step_id, ok=ok, result=text))
        await on_event(step_event("token", text=text))
    return ChatResult(
        response=text,
        tools_used=[delegation.TOOL_NAME],
        tool_calls=[ToolCallRecord(name=delegation.TOOL_NAME, arguments=arguments, result=text)],
        provider_id=route.backend,
        model=route.model,
        total_tokens=route.prompt_tokens,
        input_tokens=route.prompt_tokens,
        output_tokens=0,
        model_note=f"routed straight to {label} ({route.entry.id}, {route.confidence}%)",
    )
