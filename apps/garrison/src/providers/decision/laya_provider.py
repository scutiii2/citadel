"""Typed-question provider: answers caller-supplied choice, score and noul questions about a short
text. No generated text and no tool calls.

`answer` hands every request to llm/triage_flow.py: the Laya service answers with a decision strategy
(llm/laya_model.py), then the fallback classifier (config_tuning.json's `classifier.triage_fallback`
and a backend of the triage chain in llm/decision.py) is asked about what the Laya models could not settle.
A `local_only` request never reaches the fallback. Without the fallback, nothing leaves the machine."""

from __future__ import annotations

import json
import math
import logging
from dataclasses import dataclass
from typing import Any

import anyio.to_thread

from src.providers import cancellation
from src.providers.decision import decision, laya_model
from src.providers.base_provider import ChatCancelled, ChatResult, step_event

PROVIDER_ID = "laya"
DEFAULT_MODEL = "convaiinnovations/laya"
TYPED_MODEL = "typed-decisions"  # the second Laya checkpoint of the flow (llm/triage_flow.py)
VENDOR_LABEL = "Laya (local)"
SUPPORTS_STREAMING = True
CONTEXT_WINDOW = 512
MAX_INPUT_CHARS = 4000
# An initial review gate, not a measured accuracy guarantee. Validate against
# representative local examples before using these answers for actions.
MIN_CONFIDENCE = 0.7

_REQUEST_KEYS = {"text", "questions", "min_confidence", "trace", "local_only", "strategy"}
# Jev's labels for a noul question that gives none; the question rules themselves are the Laya service's (POST /v1/validate).
_NOUL_DEFAULTS = {"false": "No: the statement is false.", "true": "Yes: the statement is true."}

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Request:
    text: str
    questions: dict[str, dict[str, Any]]
    min_confidence: float
    # Ask the flow for the full answer with its rounds trace (llm/triage_flow.py).
    trace: bool = False
    # Only Laya's own models answer (English and typed-decisions, where classifier.triage_enabled allows them for the
    # question type): no fallback classifier (Jev).
    local_only: bool = False
    # A Laya service decision strategy that replaces the one the voter settings would choose (llm/triage_flow.py).
    strategy: str | None = None


def _fail(message: str) -> ValueError:
    return ValueError(f"Invalid Laya request: {message}")


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def parse_request(raw: str, max_chars: int = MAX_INPUT_CHARS) -> Request:
    """Validate the JSON question. Text after the first JSON object is ignored:
    delegation appends attachment references to the question string. `max_chars`
    is Laya's own limit unless a larger classifier will take the long texts."""
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
    min_confidence = data.get("min_confidence", MIN_CONFIDENCE)
    if not _is_number(min_confidence) or not 0 < min_confidence <= 1:
        raise _fail("min_confidence must be a number above 0 and at most 1")
    questions = data.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise _fail("questions must be a non-empty object")
    trace = data.get("trace", False)
    if not isinstance(trace, bool):
        raise _fail("trace must be true or false")
    local_only = data.get("local_only", False)
    if not isinstance(local_only, bool):
        raise _fail("local_only must be true or false")
    strategy = data.get("strategy")
    if "strategy" in data:
        if not _is_text(strategy):
            raise _fail("strategy must be a non-empty string")
        strategy = strategy.strip()
    return Request(text, questions, float(min_confidence), trace, local_only, strategy)


def _with_eliminated(spec: dict[str, Any], answer: dict[str, Any], eliminated: list[str]) -> dict[str, Any]:
    """A narrowed answer over the question's full option list: dropped options read 0."""
    out = dict(answer)
    out["probabilities"] = {name: answer["probabilities"].get(name, 0.0) for name in spec["criteria"]}
    out["eliminated"] = eliminated
    return out


# Laya is this provider; the fallback chain is every other backend of the triage chain.
_FALLBACK_EXCLUDE = ("laya",)


def _fallback_options(spec: dict[str, Any]) -> dict[str, str]:
    """The question's options as a classifier backend names them: choices as given, score levels
    as "0", "1", ... (lowest first) and a noul question as "false" and "true"."""
    if spec["type"] == "choice":
        return dict(spec["criteria"])
    if spec["type"] == "score":
        return {str(i): f"level {i}: {level}" for i, level in enumerate(spec["criteria"])}
    return dict(spec.get("criteria") or _NOUL_DEFAULTS)


def _fallback_answer(request: Request, spec: dict[str, Any], picked: decision.Choice) -> dict[str, Any]:
    """A backend's pick in the response shape of a Laya answer. A backend that reports a distribution
    keeps it; otherwise its confidence is the one number it gives, so the other options share what
    is left. `answered_by` marks the backend."""
    confidence = picked.confidence / 100
    out: dict[str, Any] = {"type": spec["type"]}
    if spec["type"] == "choice":
        others = [name for name in spec["criteria"] if name != picked.choice]
        share = round((1 - confidence) / len(others), 4) if others else 0.0
        out["choice"] = picked.choice
        real = picked.probabilities
        out["probabilities"] = (
            {name: round(real[name], 4) for name in spec["criteria"]} if real and set(real) == set(spec["criteria"])
            else {name: (confidence if name == picked.choice else share) for name in spec["criteria"]}
        )
    elif spec["type"] == "score":
        out["score"] = float(picked.choice)
        out["legend"] = {str(i): level for i, level in enumerate(spec["criteria"])}
    else:
        out["noul"] = confidence if picked.choice == "true" else round(1 - confidence, 4)
    out["answer_confidence"] = confidence
    out["uncertain"] = confidence < request.min_confidence
    out["answered_by"] = picked.backend
    return out


def _ask_fallback(request: Request, qids: list[str]) -> tuple[dict[str, dict[str, Any]], int, list[str]]:
    """The fallback backends' answers for `qids`, the prompt tokens they used and why any question got none.
    A failure never raises: that question just keeps Laya's answer, or none."""
    answers: dict[str, dict[str, Any]] = {}
    tokens = 0
    problems: list[str] = []
    for qid in qids:
        spec = request.questions[qid]
        question = spec["instructions"]
        if spec["type"] == "score":
            question += " Pick the level that fits best; level 0 is the lowest."
        try:
            picked = decision.ask_choice(
                request.text, _fallback_options(spec), question, "triage",
                min_confidence=round(request.min_confidence * 100), exclude=_FALLBACK_EXCLUDE,
            )
        except decision.ClassifierError as error:
            _log.warning("the fallback classifier could not answer question %r: %s", qid, error)
            problems.append(str(error))
            continue
        tokens += picked.prompt_tokens
        answers[qid] = _fallback_answer(request, spec, picked)
    return answers, tokens, problems


def answer(raw: str) -> ChatResult:
    from src.providers.decision import triage_flow

    return triage_flow.TriageFlow().answer(raw)


def has_api_key() -> bool:
    """Compatibility with agent_config: this provider needs no API key."""
    return True


def is_available() -> bool:
    return laya_model.configured()


def prepare() -> None:
    """Warn at start-up when the Laya service is not answering; requests then fail until it does."""
    if not laya_model.configured():
        _log.warning("LAYA_SERVICE_URL is not set: no Laya model is available")
    elif not laya_model.agent().health():
        _log.warning("The Laya service does not answer yet; Laya questions fail until it does")


async def run_chat(
    question: str, history: list[dict[str, Any]], model: str | None,
    enabled_extensions: list[str], request_id: str | None = None, depth: int = 0,
    on_event: Any = None, caveman: bool = False,
) -> ChatResult:
    if model and model != DEFAULT_MODEL:
        raise ValueError(f"Laya only supports {DEFAULT_MODEL}.")
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()
    result = await anyio.to_thread.run_sync(answer, question)
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()
    if on_event is not None:
        await on_event(step_event("token", text=result.response))
    return result


def run_interpret(text: str, model: str | None = None) -> ChatResult:
    raise ValueError("Laya does not support summarization or free-form text generation. Use ask with a JSON question request.")
