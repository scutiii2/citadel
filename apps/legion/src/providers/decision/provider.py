"""Decision provider adapter: typed questions answered by the agent's list of decision models, without generated
text or tools."""
from __future__ import annotations

import json
import math
import logging
from dataclasses import dataclass
from typing import Any, Sequence
import anyio.to_thread

from src.providers import cancellation
from src.providers.base_provider import ChatCancelled, ChatResult, step_event
from src.providers.decision import strategy
from src.providers.decision.contract import DecisionError, DecisionRequest

PROVIDER_ID = "decision"
DEFAULT_MODEL = "decision"
VENDOR_LABEL = "Decision (Laya, Jev)"
SUPPORTS_STREAMING = True
MAX_INPUT_CHARS = 16000
_REQUEST_KEYS = {"text", "questions", "min_confidence", "trace"}
_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Request:
    text: str
    questions: dict[str, dict[str, Any]]
    min_confidence: float | None
    # Keep the caller's request for gateway trace details.
    trace: bool = False


def _fail(message: str) -> ValueError:
    return ValueError(f"Invalid decision request: {message}")


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def parse_request(raw: str, max_chars: int = MAX_INPUT_CHARS, default_confidence: float | None = None) -> Request:
    """Validate the JSON question. Text after the first JSON object is ignored:
    delegation appends attachment references to the question string. `max_chars`
    bounds the complete input accepted by the decision wrapper."""
    try:
        data, _ = json.JSONDecoder().raw_decode(raw.lstrip())
    except ValueError as error:
        raise _fail('the question must be JSON: {"text": "...", "questions": {...}}') from error
    if not isinstance(data, dict):
        raise _fail("the question must be a JSON object")
    unknown = set(data) - _REQUEST_KEYS
    if unknown:
        raise _fail(f"unknown field(s): {', '.join(sorted(unknown))}")
    text = data.get("text")
    if not _is_text(text):
        raise _fail("text must be a non-empty string")
    if len(text) > max_chars:
        raise _fail(f"text must be at most {max_chars} characters; send a shorter excerpt")
    min_confidence = data.get("min_confidence", default_confidence)
    if min_confidence is not None and (not _is_number(min_confidence) or not 0 < min_confidence <= 1):
        raise _fail("min_confidence must be a number above 0 and at most 1")
    questions = data.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise _fail("questions must be a non-empty object")
    for qid, question in questions.items():
        where = f"questions.{qid}"
        if not _is_text(qid) or not isinstance(question, dict):
            raise _fail(f"{where} must have a non-empty id and an object definition")
        kind = question.get("type")
        if kind not in ("choice", "score", "noul"):
            raise _fail(f"{where}.type must be choice, score or noul")
        if not _is_text(question.get("instructions")):
            raise _fail(f"{where}.instructions must be a non-empty string")
        criteria = question.get("criteria")
        if kind == "score":
            if not isinstance(criteria, list) or not criteria or not all(_is_text(level) for level in criteria):
                raise _fail(f"{where}.criteria must be a non-empty list of level descriptions")
        elif kind == "choice" or "criteria" in question:
            if not isinstance(criteria, dict) or not criteria or not all(
                    _is_text(key) and _is_text(value) for key, value in criteria.items()):
                raise _fail(f"{where}.criteria must be a non-empty object of option descriptions")
            if kind == "noul" and set(criteria) != {"false", "true"}:
                raise _fail(f"{where}.criteria must contain false and true labels")
    trace = data.get("trace", False)
    if not isinstance(trace, bool):
        raise _fail("trace must be true or false")
    return Request(text, questions, None if min_confidence is None else float(min_confidence), trace)


# Per-question detail the Laya service reports; only a `trace` request carries it back to the caller.
_TRACE_KEYS = ("rounds", "voters", "options", "disagreement", "resolved_by", "eliminated")


def _compact(answer: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in answer.items() if key not in _TRACE_KEYS}


def answer(raw: str, models: Sequence[str], min_confidence: float | None = None) -> ChatResult:
    request = parse_request(raw, default_confidence=min_confidence)
    try:
        result = strategy.run(tuple(models), DecisionRequest(request.text, request.questions, request.min_confidence))
    except DecisionError as error:
        raise ValueError(f"The decision models could not answer: {error}") from error
    answers = result.answers if request.trace else {qid: _compact(a) for qid, a in result.answers.items()}
    body = {"answers": answers, "tokens": result.tokens}
    return ChatResult(response=json.dumps(body), tools_used=[], tool_calls=[], provider_id=PROVIDER_ID,
                      model="+".join(models), total_tokens=result.tokens, input_tokens=result.tokens, output_tokens=0)


def has_api_key() -> bool:
    return True


def _models() -> tuple[str, ...]:
    from src.agents import agent_spec
    return agent_spec.current().llm.gateway_names


def is_available() -> bool:
    return any(gateway.available() for gateway in strategy.default_gateways(_models()).values())


def prepare() -> None:
    for name, gateway in strategy.default_gateways(_models()).items():
        if not gateway.available():
            _log.warning("The %s decision gateway is unavailable", name)


async def run_chat(
    question: str, history: list[dict[str, Any]], model: str | None,
    request_id: str | None = None, depth: int = 0,
    on_event: Any = None, caveman: bool = False,
) -> ChatResult:
    from src.agents import agent_spec
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()
    llm = agent_spec.current().llm
    result = await anyio.to_thread.run_sync(answer, question, llm.gateway_names, llm.min_confidence)
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()
    if on_event is not None:
        await on_event(step_event("token", text=result.response))
    return result


def run_interpret(text: str, model: str | None = None) -> ChatResult:
    raise ValueError("The decision provider does not support free-form text generation. Use ask with a JSON question request.")
