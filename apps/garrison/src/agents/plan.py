"""A local checklist tool whose state lasts only for one provider turn."""

from __future__ import annotations

import json
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from src.llm.base_provider import OnEvent, step_event

TOOL_NAME = "update_plan"
STATUSES = ["pending", "in_progress", "done"]
UNCHANGED = "The plan is unchanged, so it was not updated. Continue the task."


@dataclass(frozen=True)
class PlanPolicy:
    """Whether this turn's agent is offered update_plan, and how it should use it.

    `chat` is the user's chat toggle, `agent` the agent file's plan_tool key; the
    tool is offered only when both allow it. `lean` asks for an update only when
    an item changes status. Same ContextVar shape as questions.py: set per ask()
    call, so a provider's tool list needs no extra parameters."""

    chat: bool = True
    agent: bool = True
    lean: bool = True

    @property
    def offered(self) -> bool:
        return self.chat and self.agent


_policy: ContextVar[PlanPolicy] = ContextVar("plan_policy", default=PlanPolicy())


def bind(policy: PlanPolicy) -> Token:
    return _policy.set(policy)


def reset(token: Token) -> None:
    _policy.reset(token)


def current() -> PlanPolicy:
    return _policy.get()


def tool_description(lean: bool = False) -> str:
    text = (
        "Keep a short checklist for a task with three or more distinct steps. Send the full updated list each time, "
        "with pending, in_progress, or done for each item. Use at most one in_progress item. "
        "Do not use this tool for a single answer or a task of one or two steps. An empty list clears the plan."
    )
    if lean:
        text += (
            " Call it only when an item changes status (an item starts or finishes) or when the steps change. "
            "Never call it to resend an unchanged list."
        )
    return text


def tool_parameters() -> dict[str, Any]:
    return {
        "type": "object", "required": ["items"], "additionalProperties": False,
        "properties": {"items": {
            "type": "array", "maxItems": 50,
            "items": {
                "type": "object", "required": ["text", "status"], "additionalProperties": False,
                "properties": {
                    "text": {"type": "string", "minLength": 1, "maxLength": 300},
                    "status": {"type": "string", "enum": STATUSES},
                },
            },
        }},
    }


class Checklist:
    """Validate complete snapshots and emit them without external tool dispatch."""

    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    async def handle(self, name: str, arguments: Any, on_event: OnEvent | None) -> tuple[str, bool] | None:
        if name != TOOL_NAME:
            return None
        raw = arguments.get("items") if isinstance(arguments, dict) else None
        if not isinstance(raw, list) or len(raw) > 50:
            return "update_plan needs an items list with at most 50 entries.", False
        items = []
        for item in raw:
            if not isinstance(item, dict) or set(item) != {"text", "status"}:
                return "Each plan item needs text and status only.", False
            text = item["text"]
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 300 or item["status"] not in STATUSES:
                return "Plan items need 1–300 characters and pending, in_progress, or done status.", False
            items.append({"text": text.strip(), "status": item["status"]})
        if sum(item["status"] == "in_progress" for item in items) > 1:
            return "Only one plan item may be in_progress.", False
        if current().lean and items == self.items:
            return UNCHANGED, True
        self.items = items
        if on_event:
            await on_event(step_event("plan_update", items=items))
        return json.dumps({"items": items}), True
