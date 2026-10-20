"""Local typed-question provider: answers caller-supplied choice, score and
noul questions about a short text. No generated text and no tool calls.

`LayaQuestions.answer` hands every request to llm/triage_flow.py: Laya English, then the
typed-decisions checkpoint, then the fallback classifier (config_tuning.json's `classifier.triage_fallback`
and a backend of the triage chain in llm/decision.py), each against its own threshold. A `local_only`
request never reaches the fallback. Without the fallback, nothing here leaves the machine."""

from __future__ import annotations

import importlib.util
import json
import math
import logging
import threading
from dataclasses import dataclass
from typing import Any

import anyio.to_thread

from src.core.catalog import catalog
from src.llm import cancellation, decision
from src.llm.base_provider import ChatCancelled, ChatResult, step_event

PROVIDER_ID = "laya"
DEFAULT_MODEL = "convaiinnovations/laya"
TYPED_MODEL = "typed-decisions"  # the second local checkpoint of the flow (llm/triage_flow.py)
VENDOR_LABEL = "Laya (local)"
SUPPORTS_STREAMING = True
CONTEXT_WINDOW = 512
MAX_INPUT_CHARS = 4000
# An initial review gate, not a measured accuracy guarantee. Validate against
# representative local examples before using these answers for actions.
MIN_CONFIDENCE = 0.7
MAX_QUESTIONS = 8
MIN_OPTIONS = 2
MAX_OPTIONS = 10

_REQUEST_KEYS = {"text", "questions", "min_confidence", "trace", "local_only"}
_QUESTION_KEYS = {"type", "instructions", "criteria"}
_QUESTION_TYPES = ("choice", "score", "noul")
_NOUL_KEYS = {"false", "true"}
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


def _fail(message: str) -> ValueError:
    return ValueError(f"Invalid Laya request: {message}")


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _question(qid: str, spec: Any) -> dict[str, Any]:
    if not _is_text(qid):
        raise _fail("question ids must be non-empty strings")
    if not isinstance(spec, dict):
        raise _fail(f"question {qid!r} must be an object")
    unknown = set(spec) - _QUESTION_KEYS
    if unknown:
        raise _fail(f"question {qid!r} has unknown field(s): {', '.join(sorted(unknown))}")
    qtype = spec.get("type")
    if qtype not in _QUESTION_TYPES:
        raise _fail(f"question {qid!r} type must be choice, score or noul")
    if not _is_text(spec.get("instructions")):
        raise _fail(f"question {qid!r} needs non-empty instructions")
    criteria = spec.get("criteria")
    if qtype == "choice":
        valid = (isinstance(criteria, dict) and MIN_OPTIONS <= len(criteria) <= MAX_OPTIONS
                 and all(_is_text(k) and _is_text(v) for k, v in criteria.items()))
        rule = f"an object of {MIN_OPTIONS} to {MAX_OPTIONS} option: description strings"
    elif qtype == "score":
        valid = (isinstance(criteria, list) and MIN_OPTIONS <= len(criteria) <= MAX_OPTIONS
                 and all(_is_text(v) for v in criteria))
        rule = f"a list of {MIN_OPTIONS} to {MAX_OPTIONS} level description strings, lowest first"
    else:
        valid = criteria is None or (isinstance(criteria, dict) and set(criteria) == _NOUL_KEYS
                                     and all(_is_text(v) for v in criteria.values()))
        rule = 'omitted, or an object with exactly the keys "false" and "true"'
    if not valid:
        raise _fail(f"question {qid!r} ({qtype}) criteria must be {rule}")
    out: dict[str, Any] = {"type": qtype, "instructions": spec["instructions"]}
    if criteria is not None:
        out["criteria"] = criteria
    return out


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
    if not isinstance(questions, dict) or not 1 <= len(questions) <= MAX_QUESTIONS:
        raise _fail(f"questions must be an object with 1 to {MAX_QUESTIONS} entries")
    trace = data.get("trace", False)
    if not isinstance(trace, bool):
        raise _fail("trace must be true or false")
    local_only = data.get("local_only", False)
    if not isinstance(local_only, bool):
        raise _fail("local_only must be true or false")
    return Request(
        text, {qid: _question(qid, spec) for qid, spec in questions.items()}, float(min_confidence), trace, local_only,
    )


def _asks_local_only(raw: str) -> bool:
    """True when the question is a JSON object with `local_only: true`. Anything else is left to parse_request."""
    try:
        data, _ = json.JSONDecoder().raw_decode(raw.lstrip())
    except ValueError:
        return False
    return isinstance(data, dict) and data.get("local_only") is True


def _unit(value: Any) -> float:
    if not _is_number(value) or not 0 <= value <= 1:
        raise ValueError("invalid probability")
    return float(value)


def _answer(spec: dict[str, Any], raw: dict[str, Any], min_confidence: float) -> dict[str, Any]:
    """One validated answer in the response shape; raises on anything the
    request did not allow or that is not a finite in-range number."""
    confidence = _unit(raw["answer_confidence"])
    qtype = spec["type"]
    out: dict[str, Any] = {"type": qtype}
    if qtype == "choice":
        choice = raw["choice"]
        probabilities = raw["probabilities"]
        if choice not in spec["criteria"] or set(probabilities) != set(spec["criteria"]):
            raise ValueError("unknown choice")
        out["choice"] = choice
        out["probabilities"] = {key: _unit(value) for key, value in probabilities.items()}
    elif qtype == "score":
        score = raw["score"]
        if not _is_number(score) or not 0 <= score <= len(spec["criteria"]) - 1:
            raise ValueError("invalid score")
        out["score"] = round(float(score), 4)
        out["legend"] = {str(i): level for i, level in enumerate(spec["criteria"])}
    else:
        out["noul"] = _unit(raw["noul"])
    out["answer_confidence"] = confidence
    out["uncertain"] = confidence < min_confidence
    return out


def _kept_options(average: dict[str, float], ratio: float) -> list[str]:
    """The options worth asking about again, in the question's order: those at least `ratio` of the
    leader's averaged probability, and never fewer than two."""
    top = max(average.values())
    kept = [name for name in average if average[name] >= ratio * top]
    if len(kept) < MIN_OPTIONS:
        kept = sorted(average, key=average.__getitem__, reverse=True)[:MIN_OPTIONS]
    return [name for name in average if name in kept]


def _round(step: str, answer: dict[str, Any], options: list[str] | None = None) -> dict[str, Any]:
    """One model call of a question's review, for the answer's `rounds` trace."""
    out: dict[str, Any] = {
        "step": step, "choice": answer["choice"],
        "probabilities": {name: round(value, 4) for name, value in answer["probabilities"].items()},
        "confidence": answer["answer_confidence"],
    }
    if options is not None:
        out["options"] = options
    return out


def _average_round(average: dict[str, float], eliminated: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"step": "average", "probabilities": {name: round(value, 4) for name, value in average.items()}}
    if eliminated:
        out["eliminated"] = eliminated
    return out


def _with_eliminated(spec: dict[str, Any], answer: dict[str, Any], eliminated: list[str]) -> dict[str, Any]:
    """A narrowed answer over the question's full option list: dropped options read 0."""
    out = dict(answer)
    out["probabilities"] = {name: answer["probabilities"].get(name, 0.0) for name in spec["criteria"]}
    out["eliminated"] = eliminated
    return out


class _InputTooLong(ValueError):
    """Laya could not read the whole text, so it gave no answers."""


_TOO_LONG = (
    "Laya could not read the complete input. Send a shorter text or fewer, shorter questions; "
    "no answers were returned."
)


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


@catalog
class LayaQuestions:
    """Load one English Laya checkpoint and answer typed questions about a text.

    Lazy load + lock; an engine can be injected for offline contract tests. `checkpoint` picks the Laya
    checkpoint (the English root unless told otherwise), `window` the token window a call reads (CONTEXT_WINDOW
    unless told otherwise) and `typed` injects the typed-decisions model of the flow.
    """

    def __init__(
        self, engine: Any = None, checkpoint: str = DEFAULT_MODEL, window: int | None = None,
        typed: "LayaQuestions | None" = None,
        local_only: bool = False,
    ) -> None:
        self._engine = engine
        self._checkpoint = checkpoint
        self.window = window
        self._typed = typed
        self._local_only = local_only
        self._lock = threading.Lock()

    def _load(self) -> Any:
        # Called only while holding _lock, including during inference.
        if self._engine is None:
            try:
                import laya
            except ImportError as error:
                raise RuntimeError('Laya is not installed: pip install -e .') from error
            checkpoint = self._checkpoint
            if self._local_only:
                from src.agents.router_models import cached_checkpoint

                checkpoint = cached_checkpoint(checkpoint)
            self._engine = laya.load(checkpoint)
        return self._engine

    def _flow_models(self) -> dict[str, "LayaQuestions"]:
        """The two local voters of the flow: this (English) model and the typed-decisions one, both on the
        flow's window. The typed model loads on first use."""
        self.window = decision.settings().triage_window
        english, typed = decision.TRIAGE_VOTERS[:2]
        return {english: self, typed: self._typed_model()}

    def _typed_model(self) -> "LayaQuestions":
        if self._typed is None:
            self._typed = LayaQuestions(checkpoint=TYPED_MODEL)
        self._typed.window = decision.settings().triage_window
        return self._typed

    def _warm(self) -> None:
        """Load this one checkpoint now."""
        with self._lock:
            self._load()

    def prepare(self) -> None:
        """Warm the models before registering this agent as running: English and the typed-decisions one (the
        flow and every `local_only` request use it)."""
        self._warm()
        self._typed_model()._warm()

    def _answer_local(self, raw: str) -> ChatResult:
        """Laya's own models only: English, then the typed-decisions checkpoint when English is unsure (the flow
        without Jev). A text Laya cannot read whole raises, as without a fallback."""
        from src.llm import triage_flow  # imported here: triage_flow imports this module

        return triage_flow.TriageFlow(self._flow_models(), use_fallback=False).answer(raw)

    def answer(self, raw: str) -> ChatResult:
        if _asks_local_only(raw):
            return self._answer_local(raw)
        from src.llm import triage_flow  # imported here: triage_flow imports this module

        return triage_flow.TriageFlow(self._flow_models()).answer(raw)

    def _laya_answers(self, request: Request, check=None) -> tuple[dict[str, dict[str, Any]], int]:
        if check:
            while not self._lock.acquire(timeout=min(.05, check())):
                check()
        else:
            self._lock.acquire()
        try:
            if check:
                check()
            prediction = self._load().predict(request.text, request.questions, max_len=self.window or CONTEXT_WINDOW)
        finally:
            self._lock.release()
        try:
            usage = prediction.get("usage", {})
            incomplete = usage.get("truncated") or usage.get("state_tokens_dropped", 0)
        except AttributeError as error:
            raise ValueError("Laya returned an invalid result; no answers were returned.") from error
        if incomplete:
            raise _InputTooLong(_TOO_LONG)
        try:
            answers = {
                qid: _answer(spec, prediction["answers"][qid], request.min_confidence)
                for qid, spec in request.questions.items()
            }
            input_tokens = usage["input_tokens"]
            if isinstance(input_tokens, bool) or not isinstance(input_tokens, int) or input_tokens < 0:
                raise ValueError("invalid token usage")
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise ValueError("Laya returned an invalid result; no answers were returned.") from error
        return answers, input_tokens


_questions = LayaQuestions()


def answer_typed(request: Request) -> tuple[dict[str, dict[str, Any]], int]:
    """Laya's own answers to a validated request and the tokens it read; no remote fallback.
    Raises ValueError when the text does not fit its window (llm/laya_classifier.py)."""
    return _questions._laya_answers(request)


def has_api_key() -> bool:
    """Compatibility with agent_config: this local provider needs no API key."""
    return True


def is_available() -> bool:
    return importlib.util.find_spec("laya") is not None


def prepare() -> None:
    _questions.prepare()


async def run_chat(
    question: str, history: list[dict[str, Any]], model: str | None,
    enabled_extensions: list[str], request_id: str | None = None, depth: int = 0,
    on_event: Any = None, caveman: bool = False,
) -> ChatResult:
    if model and model != DEFAULT_MODEL:
        raise ValueError(f"Laya only supports {DEFAULT_MODEL}.")
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()
    result = await anyio.to_thread.run_sync(_questions.answer, question)
    if cancellation.is_cancelled(request_id):
        raise ChatCancelled()
    if on_event is not None:
        await on_event(step_event("token", text=result.response))
    return result


def run_interpret(text: str, model: str | None = None) -> ChatResult:
    raise ValueError("Laya does not support summarization or free-form text generation. Use ask with a JSON question request.")
