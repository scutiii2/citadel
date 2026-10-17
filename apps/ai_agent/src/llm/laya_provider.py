"""Local typed-question provider: answers caller-supplied choice, score and
noul questions about a short text. No generated text and no tool calls.

When config_tuning.json's `classifier.triage_fallback` is on and a backend of the
triage chain is available (llm/decision.py), that classifier answers what Laya
cannot: questions Laya is unsure of, and texts too long for Laya's window.
Without that, nothing here leaves the machine.

With `classifier.triage_flow` set to "sequential", `LayaQuestions.answer` hands the request to
llm/triage_flow.py instead: Laya English, then the typed-decisions checkpoint, then the fallback,
each against its own threshold."""

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
TYPED_MODEL = "typed-decisions"  # the second local checkpoint of the sequential flow (llm/triage_flow.py)
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

_REQUEST_KEYS = {"text", "questions", "min_confidence", "trace"}
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
    # Ask the sequential flow for the full answer with its rounds trace (llm/triage_flow.py).
    trace: bool = False


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
    return Request(
        text, {qid: _question(qid, spec) for qid, spec in questions.items()}, float(min_confidence), trace,
    )


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


def _average(first: dict[str, float], second: dict[str, float]) -> dict[str, float]:
    return {name: (first[name] + second[name]) / 2 for name in first}


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


def _pair(
    request: Request, laya: dict[str, Any], remote: dict[str, Any], rounds: list[dict[str, Any]],
) -> dict[str, Any]:
    """Two options are left and Laya and the fallback still pick differently. Weigh each model's
    probabilities by its own confidence, take the absolute difference per option, and compare the two
    differences: when they are far apart the option with the bigger one is the answer, otherwise the
    answer is unsure and could be either (`candidates`). Either way `also_check` names the option(s) the
    reader should still look at, with a one-line `note`. The steps are appended to `rounds`."""
    by = remote["answered_by"]
    options = list(laya["probabilities"])
    scaled_laya = {o: laya["answer_confidence"] * laya["probabilities"][o] for o in options}
    scaled_remote = {o: remote["answer_confidence"] * remote["probabilities"][o] for o in options}
    difference = {o: abs(scaled_remote[o] - scaled_laya[o]) for o in options}
    larger, smaller = max(difference.values()), min(difference.values())
    decided = larger > 0 and smaller < decision.settings().triage_pair_ratio * larger
    total = sum(difference.values())
    share = {o: (difference[o] / total if total else 1 / len(options)) for o in options}
    # A tie goes to the pick of the more confident of the two.
    leader = laya["choice"] if laya["answer_confidence"] >= remote["answer_confidence"] else remote["choice"]
    choice = max(options, key=lambda o: (round(difference[o], 6), o == leader))
    rounds += [
        {"step": f"laya x confidence", "options": options, "probabilities": _rounded(scaled_laya)},
        {"step": f"{by} x confidence", "options": options, "probabilities": _rounded(scaled_remote)},
        {"step": "difference", "options": options, "probabilities": _rounded(difference),
         "choice": choice if decided else "unsure: " + " or ".join(options)},
    ]
    out: dict[str, Any] = {
        "type": "choice", "choice": choice, "probabilities": _rounded(share), "answer_confidence": round(share[choice], 4),
        "uncertain": not decided, "answered_by": f"laya+{by}", "resolved_by": "pair",
        "disagreement": {"laya": laya["choice"], by: remote["choice"]},
    }
    other = [o for o in options if o != choice]
    who = {"jev": "Jev", "jev_vercel": "Jev (Vercel)"}.get(by, by)
    # The models disagreed, so the reader is always pointed at the option that lost, too.
    out["also_check"] = other
    if decided:
        out["note"] = f"Laya and {who} disagreed; {choice} is the stronger answer, but also check {' and '.join(other)}."
    else:
        out["candidates"] = options
        out["note"] = f"Laya and {who} disagreed and the weighed answers are too close to call: it could be {' or '.join(options)}; check both."
    return out


def _rounded(values: dict[str, float]) -> dict[str, float]:
    return {name: round(value, 4) for name, value in values.items()}


def _blend(request: Request, laya: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    """Laya's and the fallback's answers to one choice question as a single answer: the averaged
    distribution, the higher confidence when both pick the same option and the lower one when they do
    not (that case is always uncertain and records who picked what)."""
    average = _average(laya["probabilities"], remote["probabilities"])
    agree = laya["choice"] == remote["choice"]
    confidence = (max if agree else min)(laya["answer_confidence"], remote["answer_confidence"])
    # A tie goes to the pick of the more confident of the two.
    leader = laya["choice"] if laya["answer_confidence"] >= remote["answer_confidence"] else remote["choice"]
    out: dict[str, Any] = {
        "type": "choice", "choice": max(average, key=lambda name: (round(average[name], 6), name == leader)),
        "probabilities": {name: round(value, 4) for name, value in average.items()},
        "answer_confidence": confidence, "uncertain": not agree or confidence < request.min_confidence,
        "answered_by": f"laya+{remote['answered_by']}",
    }
    if not agree:
        out["disagreement"] = {"laya": laya["choice"], remote["answered_by"]: remote["choice"]}
    out["rounds"] = [_round("laya", laya), _round(remote["answered_by"], remote), _average_round(average)]
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


def _fallback_enabled() -> bool:
    return decision.settings().triage_fallback and decision.available("triage", _FALLBACK_EXCLUDE)


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
    unless told otherwise) and `typed` injects the typed-decisions model of the sequential flow.
    """

    def __init__(
        self, engine: Any = None, checkpoint: str = DEFAULT_MODEL, window: int | None = None,
        typed: "LayaQuestions | None" = None,
    ) -> None:
        self._engine = engine
        self._checkpoint = checkpoint
        self.window = window
        self._typed = typed
        self._lock = threading.Lock()

    def _load(self) -> Any:
        # Called only while holding _lock, including during inference.
        if self._engine is None:
            try:
                import laya
            except ImportError as error:
                raise RuntimeError('Laya is not installed: pip install -e .') from error
            self._engine = laya.load(self._checkpoint)
        return self._engine

    def _sequential(self) -> bool:
        return decision.settings().triage_flow == "sequential"

    def _flow_models(self) -> dict[str, "LayaQuestions"]:
        """The two local voters of the sequential flow: this (English) model and the typed-decisions one, both on the
        flow's window. The typed model loads on first use."""
        window = decision.settings().triage_window
        if self._typed is None:
            self._typed = LayaQuestions(checkpoint=TYPED_MODEL)
        self.window = self._typed.window = window
        english, typed = decision.TRIAGE_VOTERS[:2]
        return {english: self, typed: self._typed}

    def _warm(self) -> None:
        """Load this one checkpoint now."""
        with self._lock:
            self._load()

    def prepare(self) -> None:
        """Warm the model(s) before registering this agent as running: the typed-decisions one too for the
        sequential flow."""
        self._warm()
        if self._sequential():
            self._flow_models()[decision.TRIAGE_VOTERS[1]]._warm()

    def answer(self, raw: str) -> ChatResult:
        if self._sequential():
            from src.llm import triage_flow  # imported here: triage_flow imports this module

            return triage_flow.TriageFlow(self._flow_models()).answer(raw)
        fallback = _fallback_enabled()
        request = parse_request(raw, decision.settings().max_input_chars if fallback else MAX_INPUT_CHARS)
        answers: dict[str, dict[str, Any]] | None = None
        input_tokens = 0
        unreadable: _InputTooLong | None = None
        if len(request.text) <= MAX_INPUT_CHARS:
            try:
                answers, input_tokens = self._laya_answers(request)
            except _InputTooLong as error:
                if not fallback:
                    raise
                unreadable = error
        # The fallback takes every question when Laya could not read the text, else only those Laya is unsure of.
        pending = list(request.questions) if answers is None else [q for q, a in answers.items() if a["uncertain"]]
        remote: dict[str, dict[str, Any]] = {}
        if fallback and pending:
            remote, remote_tokens, problems = _ask_fallback(request, pending)
            input_tokens += remote_tokens
            if answers is not None:
                # Laya read the text: weigh its answer with the fallback's (choice questions only).
                for qid in list(remote):
                    if request.questions[qid]["type"] == "choice":
                        remote[qid], extra_tokens = self._narrow(request, qid, answers[qid], remote[qid])
                        input_tokens += extra_tokens
            if answers is None and len(remote) < len(pending):
                # Nothing readable from Laya and the fallback could not cover it: no partial answers.
                reason = f" The fallback classifier could not answer either ({problems[0]})." if problems else ""
                raise _InputTooLong(str(unreadable or _TOO_LONG) + reason)
        answers = {qid: (remote.get(qid) or (answers or {})[qid]) for qid in request.questions}
        result = {"answers": answers, "uncertain": any(a["uncertain"] for a in answers.values())}
        note = (
            f"The fallback classifier reviewed {len(remote)} question(s) that Laya was unsure of or could not "
            f"read (answered by {', '.join(sorted({a['answered_by'] for a in remote.values()}))})."
        ) if remote else ""
        return ChatResult(
            response=json.dumps(result), provider_id=PROVIDER_ID, model=DEFAULT_MODEL,
            input_tokens=input_tokens, output_tokens=0, total_tokens=input_tokens,
            # State length alone excludes the question heads; don't invent a
            # context-window reading or count the JSON as generated tokens.
            context_tokens=None, model_note=note,
        )

    def _narrow(
        self, request: Request, qid: str, laya: dict[str, Any], remote: dict[str, Any],
    ) -> tuple[dict[str, Any], int]:
        """One choice question Laya and the fallback both answered. If their confidences differ by at
        least `triage_confidence_gap`, the more confident one's answer stands as it is. Otherwise: average their probabilities, drop
        the options far below the rest and ask again over what is left, Laya first and the fallback only
        if Laya is still unsure. With nothing to drop, the two answers are blended. Returns the answer and
        the extra tokens read; if Laya cannot take the narrowed question the fallback's answer stands."""
        spec = request.questions[qid]
        settings = decision.settings()
        laya_confidence, remote_confidence = laya["answer_confidence"], remote["answer_confidence"]
        gap = abs(laya_confidence - remote_confidence)
        if gap >= settings.triage_confidence_gap - 1e-9:
            by = "laya" if laya_confidence > remote_confidence else remote["answered_by"]
            winner = laya if laya_confidence > remote_confidence else remote
            rounds = [
                _round("laya", laya), _round(remote["answered_by"], remote),
                {"step": "gap", "gap": round(gap, 4), "deferred_to": by},
            ]
            return {**winner, "answered_by": by, "deferred_to": by, "rounds": rounds}, 0
        average = _average(laya["probabilities"], remote["probabilities"])
        ratio = settings.triage_prune_ratio
        kept = _kept_options(average, ratio) if ratio > 0 else list(average)
        if len(kept) == len(average):
            if len(average) == 2 and laya["choice"] != remote["choice"]:
                rounds = [_round("laya", laya), _round(remote["answered_by"], remote)]
                return {**_pair(request, laya, remote, rounds), "rounds": rounds}, 0
            return _blend(request, laya, remote), 0
        eliminated = [name for name in average if name not in kept]
        rounds = [_round("laya", laya), _round(remote["answered_by"], remote), _average_round(average, eliminated)]
        narrowed = Request(
            request.text, {qid: {**spec, "criteria": {name: spec["criteria"][name] for name in kept}}}, request.min_confidence,
        )
        try:
            laya_answers, tokens = self._laya_answers(narrowed)
        except (ValueError, RuntimeError) as error:
            _log.warning("Laya could not take the narrowed question %r: %s", qid, error)
            rounds.append({"step": "laya", "options": kept, "failed": str(error)})
            return {**remote, "rounds": rounds}, 0
        final = {**laya_answers[qid], "answered_by": "laya"}
        rounds.append(_round("laya", final, kept))
        if final["uncertain"]:
            again, extra, _ = _ask_fallback(narrowed, [qid])
            tokens += extra
            if qid in again:
                second = again[qid]
                rounds.append(_round(second["answered_by"], second, kept))
                final = _pair(request, final, second, rounds) if len(kept) == 2 and second["choice"] != final["choice"] else second
        return {**_with_eliminated(spec, final, eliminated), "rounds": rounds}, tokens

    def _laya_answers(self, request: Request) -> tuple[dict[str, dict[str, Any]], int]:
        with self._lock:
            prediction = self._load().predict(request.text, request.questions, max_len=self.window or CONTEXT_WINDOW)
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
