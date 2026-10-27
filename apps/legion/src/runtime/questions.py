"""Asking the user clickable questions (the ask_user tool).

Same shape as approvals.py: a provider's tool loop calls `handle()` for the
ask_user tool; it emits a ``question_request`` event to the caller and waits on
a broker until the user answers through the ``answer_question`` MCP tool.

Unlike an approval there is no short timeout: the user may be deciding, so the
wait lasts until they answer, skip or press Stop. While it waits it sends a
``keepalive`` event every `KEEPALIVE_SECONDS` so no proxy or read timeout sees
an idle stream. A question left open for `MAX_WAIT_SECONDS` counts as no answer,
so an abandoned browser cannot hold a turn forever.

The policy travels in a ContextVar like approvals.py's, set per ask() call; a
delegated agent never gets an enabled policy.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from src.agents.roles.orchestrator import ask_user
from src.runtime.broker import Broker
from src.providers.base_provider import ChatCancelled, OnEvent, step_event

MAX_WAIT_SECONDS = 3600.0
KEEPALIVE_SECONDS = 20.0
POLL_SECONDS = 0.5

NO_CHANNEL = "There is no way to ask the user a question from here, so nothing was asked. Continue with your best judgement."
NOT_OFFERED = "ask_user is not available in this conversation, so nothing was asked. Continue with your best judgement."
SKIPPED = "The user skipped these questions. Continue with your best judgement and say what you assumed."
TIMED_OUT = "The user did not answer in time. Continue with your best judgement and say what you assumed."


@dataclass
class QuestionPolicy:
    enabled: bool = False


_policy: ContextVar[QuestionPolicy] = ContextVar("question_policy", default=QuestionPolicy())


def bind(policy: QuestionPolicy) -> Token:
    return _policy.set(policy)


def reset(token: Token) -> None:
    _policy.reset(token)


def current() -> QuestionPolicy:
    return _policy.get()


@dataclass(frozen=True)
class Answer:
    # answered | skipped | timeout | cancelled
    outcome: str
    answers: tuple[dict[str, Any], ...] = ()


class QuestionBroker(Broker[Answer]):
    """The questions waiting on a user, keyed by (request_id, step_id).

    `answer()` and `wait()` both run on the server's event loop (the
    `answer_question` MCP tool is async), so futures are set and awaited on the
    same loop."""

    def __init__(
        self,
        timeout: float = MAX_WAIT_SECONDS,
        poll: float = POLL_SECONDS,
        keepalive: float = KEEPALIVE_SECONDS,
    ) -> None:
        super().__init__(timeout, poll)
        self._keepalive = keepalive

    async def wait(self, request_id: str, step_id: str, on_event: OnEvent | None = None) -> Answer:
        """The user's answer, or a skip, `timeout` or `cancelled`. A second
        wait on the same step replaces the first, which then reads as skipped."""
        next_keepalive = asyncio.get_running_loop().time() + self._keepalive

        async def tick(now: float) -> None:
            nonlocal next_keepalive
            if on_event is not None and now >= next_keepalive:
                await on_event(step_event("keepalive"))
                next_keepalive = now + self._keepalive

        return await self._wait(
            request_id, step_id,
            replaced=Answer("skipped"), cancelled=Answer("cancelled"), timed_out=Answer("timeout"), tick=tick,
        )

    def answer(self, request_id: str, step_id: str, answers: list[dict[str, Any]], skipped: bool) -> bool:
        """Answers a pending question. False when there is none: unknown step,
        already answered, or the turn moved on."""
        return self._resolve(request_id, step_id, Answer("skipped") if skipped else Answer("answered", tuple(answers)))


BROKER = QuestionBroker()


def format_answers(asked: list[dict[str, Any]], answers: Any) -> str:
    """What the model is told the user chose, one line per question."""
    given = list(answers or [])
    lines = ["The user answered:"]
    for index, question in enumerate(asked):
        entry = given[index] if index < len(given) and isinstance(given[index], dict) else {}
        chosen = [str(label) for label in entry.get("selected") or []]
        other = str(entry.get("other") or "").strip()
        parts = [", ".join(chosen)] if chosen else []
        if other:
            parts.append(f"other: {other}")
        lines.append(f"- {question['question']}: {'; '.join(parts) or '(no answer)'}")
    return "\n".join(lines)


async def ask(
    request_id: str | None,
    step_id: str,
    asked: list[dict[str, Any]],
    on_event: OnEvent | None,
) -> str:
    """Puts the questions to the user and returns the text the model gets as
    the tool's result. Raises ChatCancelled if the user stops the turn while
    it waits."""
    if on_event is None or not request_id:
        return NO_CHANNEL
    await on_event(step_event("question_request", id=step_id, questions=asked))
    answer = await BROKER.wait(request_id, step_id, on_event)
    await on_event(step_event("question_resolved", id=step_id, outcome=answer.outcome))
    if answer.outcome == "cancelled":
        await on_event(step_event("step_end", id=step_id, ok=False, result="Stopped before it was answered."))
        raise ChatCancelled()
    if answer.outcome == "answered":
        return format_answers(asked, answer.answers)
    return TIMED_OUT if answer.outcome == "timeout" else SKIPPED


async def handle(
    name: str,
    request_id: str | None,
    step_id: str,
    arguments: Any,
    on_event: OnEvent | None,
) -> tuple[str, bool] | None:
    """None when `name` is not the ask_user tool (the caller carries on as for
    any other tool). Otherwise (the tool's result text, whether it succeeded)."""
    if name != ask_user.TOOL_NAME:
        return None
    if not current().enabled:
        return NOT_OFFERED, False
    asked, problem = ask_user.validate(arguments)
    if asked is None:
        return str(problem), False
    return await ask(request_id, step_id, asked, on_event), True
