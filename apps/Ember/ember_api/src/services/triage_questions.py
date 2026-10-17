"""Typed questions for the Triage Assistant, asked straight from the chat page.

The user fills in a form (a yes/no question, or a multiple choice question whose
options have descriptions). This module turns that into the JSON question Laya
reads (ai_agent/src/llm/laya_provider.py) and sends it to the Triage Assistant
without the orchestrator. Option titles are written by the `title-writer` agent:
one plain model call that sees only the descriptions.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from src.services.agent_directory import AgentDirectory
from src.services.agent_gateway import AgentCallError, AgentGateway, Caller

logger = logging.getLogger(__name__)

LAYA_PROVIDER = "laya"
TITLE_AGENT_ID = "title-writer"
QID = "q"
TEXT_MAX = 4000  # Laya's own limit (laya_provider.MAX_INPUT_CHARS)
QUESTION_MAX = 300
DESCRIPTION_MAX = 300
MIN_OPTIONS = 2
MAX_OPTIONS = 10
TITLE_MAX = 30
_TOO_LONG = "complete input"  # part of ai_agent's "Laya could not read the complete input" error
_INVALID = "Invalid Laya request"

Kind = Literal["choice", "yes_no"]


class TriageUnavailable(Exception):
    """An agent could not be reached, or its answer cannot be used (a 503 for the caller)."""


class TriageRejected(Exception):
    """Laya refused the question itself, for example because the text is too long (a 422 for the caller)."""


@dataclass(frozen=True)
class Option:
    title: str
    description: str


async def _ignore_event(_event: dict[str, Any]) -> None:
    return None


def title_prompt(descriptions: list[str]) -> str:
    listing = "\n".join(f"{i}. {text}" for i, text in enumerate(descriptions, 1))
    return f"Descriptions:\n{listing}\n\nJSON array of {len(descriptions)} one-word titles:"


def clean_title(raw: object) -> str:
    """The first word of a model's title, lowercase letters, digits and '-' only; '' when nothing is left."""
    words = re.findall(r"[a-z0-9][a-z0-9_-]*", str(raw).lower())
    return words[0][:TITLE_MAX] if words else ""


def unique_titles(raw: list[object]) -> list[str]:
    """Cleaned titles, a repeat or an empty one replaced by `optionN` (N = its position) or `<title>2`, `<title>3`."""
    titles: list[str] = []
    for position, item in enumerate(raw, 1):
        title = clean_title(item) or f"option{position}"
        base, n = title, 1
        while title in titles:
            n += 1
            title = f"{base}{n}"
        titles.append(title)
    return titles


def parse_titles(response: str, count: int) -> list[str]:
    """The titles in a model's reply (a JSON array, maybe inside a code fence); `optionN` for every
    position the reply does not cover."""
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", response.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(text[text.index("["): text.rindex("]") + 1])
    except ValueError:
        data = []
    items: list[object] = [x for x in data if isinstance(x, str)] if isinstance(data, list) else []
    return unique_titles((items + [""] * count)[:count])


def build_request(kind: Kind, text: str, question: str, options: list[Option], trace: bool = False) -> str:
    """ai_agent's Laya question format: one question, id `q`."""
    if kind == "yes_no":
        spec: dict[str, Any] = {
            "type": "noul", "instructions": question,
            "criteria": {"false": "No.", "true": "Yes."},
        }
    else:
        spec = {"type": "choice", "instructions": question, "criteria": {o.title: o.description for o in options}}
    request: dict[str, Any] = {"text": text, "questions": {QID: spec}}
    if trace:
        request["trace"] = True
    return json.dumps(request)


def read_answer(kind: Kind, response: str) -> dict[str, Any]:
    """The part of Laya's answer the page shows. Raises TriageUnavailable for anything that is not the expected JSON."""
    try:
        data = json.loads(response)
        answer = data["answers"][QID]
        confidence = float(answer["answer_confidence"])
        uncertain = bool(answer["uncertain"])
        if kind == "yes_no":
            yes = float(answer["noul"])
            return {
                "kind": "yes_no", "answer": "yes" if yes >= 0.5 else "no", "yes": round(yes, 4),
                "confidence": round(confidence, 4), "uncertain": uncertain,
            }
        probabilities = {str(k): round(float(v), 4) for k, v in answer["probabilities"].items()}
        out: dict[str, Any] = {
            "kind": "choice", "choice": str(answer["choice"]), "probabilities": probabilities,
            "confidence": round(confidence, 4), "uncertain": uncertain,
        }
        for key in ("also_check", "candidates"):
            if answer.get(key):
                out[key] = [str(x) for x in answer[key]]
        if answer.get("unknown"):
            out["unknown"] = True
        if answer.get("answered_by"):
            out["answered_by"] = str(answer["answered_by"])
        if "rounds" in answer:
            out["rounds"] = answer["rounds"]
        return out
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise TriageUnavailable("The Triage Assistant gave an answer that could not be read") from error


class TriageQuestions:
    def __init__(self, gateway: AgentGateway, directory: AgentDirectory) -> None:
        self._gateway = gateway
        self._directory = directory

    async def titles(self, caller: Caller, descriptions: list[str]) -> list[str]:
        """One title per description, in order. Only the descriptions reach the model."""
        agent = await self._directory.get(TITLE_AGENT_ID)
        if agent is None:
            raise TriageUnavailable("the title-writer agent is not running")
        try:
            result = await self._gateway.interpret(agent.url, caller, title_prompt(descriptions))
        except AgentCallError as error:
            logger.info("option titles skipped: %s", error)
            raise TriageUnavailable("the title-writer agent did not answer") from error
        return parse_titles(str(result.get("response") or ""), len(descriptions))

    async def ask(
        self, caller: Caller, kind: Kind, text: str, question: str, options: list[Option], trace: bool = False
    ) -> dict[str, Any]:
        """Asks the Triage Assistant directly (no orchestrator) and returns the readable answer."""
        agent = await self._directory.find_by_provider(LAYA_PROVIDER)
        if agent is None:
            raise TriageUnavailable("the Triage Assistant is not running")
        try:
            result = await self._gateway.ask(
                agent.url, caller, question=build_request(kind, text, question, options, trace), history=[],
                request_id=uuid.uuid4().hex, caveman=False, enabled_extensions=[], on_event=_ignore_event,
            )
        except AgentCallError as error:
            message = str(error)
            if _TOO_LONG in message or _INVALID in message:
                raise TriageRejected(message) from error
            logger.info("triage question failed: %s", error)
            raise TriageUnavailable("the Triage Assistant did not answer") from error
        return read_answer(kind, str(result.get("response") or ""))
