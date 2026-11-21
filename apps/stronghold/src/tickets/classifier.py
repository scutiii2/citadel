"""Classify ticket reports through Legion's Triage Assistant."""

from __future__ import annotations

import asyncio
import math
import uuid
from typing import Any, Literal

from src.agents.gateway import Caller
from src.triage.questions import Kind, Option, TriageQuestions, TriageRejected, TriageUnavailable
from src.usage.rows import stored_rows
from src.usage.service import UsageService


class ClassifierUnavailable(Exception):
    """Classification could not run or return a usable answer."""


def _report(ticket: dict[str, Any]) -> str:
    return f"{ticket['title'][:120]}. {ticket['description'][:500]}"


class TicketClassifier:
    def __init__(self, triage: TriageQuestions, usage: UsageService, *, min_confidence: float, timeout: float) -> None:
        self._triage = triage
        self._usage = usage
        self.tune(min_confidence=min_confidence, timeout=timeout)

    def tune(self, *, min_confidence: float, timeout: float) -> None:
        self._min_confidence = min_confidence
        self._timeout = timeout

    async def _ask(self, caller: Caller, kind: Kind, text: str, question: str,
                   options: list[Option]) -> dict[str, Any] | None:
        if await self._usage.check(caller.uid) is not None:
            raise ClassifierUnavailable("usage limit reached")
        threshold = self._min_confidence
        try:
            outcome = await asyncio.wait_for(self._triage.ask(caller, kind, text, question, options), self._timeout)
        except (TriageUnavailable, TriageRejected, asyncio.TimeoutError) as error:
            raise ClassifierUnavailable("Triage could not classify the ticket") from error
        await self._usage.record(caller.uid, uuid.uuid4().hex, "ticket", None, stored_rows(outcome.result))
        answer = outcome.answer
        confidence = answer["confidence"]
        if answer["uncertain"] or answer.get("unknown") or not math.isfinite(confidence) or confidence < threshold:
            return None
        return answer

    async def same_issue(self, caller: Caller, new: dict[str, Any],
                         existing: dict[str, Any]) -> Literal["yes", "no", "uncertain"]:
        answer = await self._ask(
            caller, "yes_no", f"Report A: {_report(new)}\n\nReport B: {_report(existing)}",
            "Do Report A and Report B describe the same underlying problem or the same requested feature? "
            "Different people may word it differently.", [],
        )
        verdict = answer.get("answer") if answer else None
        return verdict if verdict in {"yes", "no"} else "uncertain"

    async def pick_tag(self, caller: Caller, ticket: dict[str, Any], tags: dict[str, str]) -> str | None:
        answer = await self._ask(
            caller, "choice", f"Ticket: {_report(ticket)}", "Which tag best describes this support ticket?",
            [Option(tag, description) for tag, description in tags.items()],
        )
        tag = answer.get("choice") if answer else None
        return tag if tag in tags else None
