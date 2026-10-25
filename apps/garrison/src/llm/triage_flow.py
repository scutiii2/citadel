"""The Triage Assistant's flow: the Laya service's decision strategy, then the fallback classifier (Jev).

Every request runs here (llm/laya_provider.py hands it over). Per question type the flow reads the local
voters that `classifier.triage_order` / `triage_enabled` allow (English then typed by default) and asks the
Laya service for the matching strategy (llm/laya_agent.py: english-then-typed, typed-then-english,
english-only or typed-only). The service owns the local rules: each model against its own confidence
threshold, narrowing the options, comparing the models (see LayaAgent/README.md). What stays here is Jev:

  1. The service settled the question: that is the answer. Nothing leaves the machine.
  2. Otherwise, with `triage_fallback` on, a backend available and Jev enabled for the type, Jev is asked over the
     options the service left (for a `choice` question; a score or noul question is simply asked).
  3. If Jev meets its threshold (`classifier.triage_thresholds`, default 0.90), its answer is the answer.
  4. If not, and more than two options are left, the options are narrowed by the average of all the models
     (`/v1/combine` on the service) and Jev is asked again.
  5. Still undecided: the service compares the models' confidence-weighted values in pairs. A clear leader is the
     provisional answer and the other options go in `also_check`; otherwise the answer is `unknown`, with the
     leading options as `candidates`. A score or noul question takes Jev's answer, flagged by its threshold.
A `min_confidence` in a request replaces every threshold. `local_only` never reaches Jev; if the service cannot
be reached, Jev (when allowed) answers alone.

What is returned is compact by default, since the orchestrator reads it on every turn: `type`, the pick (`choice`,
`score` or `noul`), `answer_confidence`, `uncertain`, `answered_by`, `probabilities` (2 decimals) and, when they
apply, `also_check`, `unknown` and `candidates`. The full answer adds `resolved_by`, `eliminated`, `disagreement`,
`note`, a `legend` for score questions and a `rounds` trace of every model call. Ask for it with `"trace": true`
in a request, or set `classifier.triage_trace`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.core import tuning_overrides

from src.llm import decision, laya_agent, laya_provider
from src.llm.base_provider import ChatResult
from src.llm.decision import TRIAGE_VOTERS
from src.llm.laya_agent import LayaServiceError
from src.llm.laya_provider import Request

_log = logging.getLogger(__name__)

ENGLISH, TYPED, JEV = TRIAGE_VOTERS
CHECKPOINTS = {ENGLISH: laya_provider.DEFAULT_MODEL, TYPED: laya_provider.TYPED_MODEL}
# The local voters of a question type, in their order -> the Laya service strategy that runs them.
_STRATEGIES = {
    (ENGLISH, TYPED): "english-then-typed", (TYPED, ENGLISH): "typed-then-english",
    (ENGLISH,): "english-only", (TYPED,): "typed-only",
}
DEFAULT_THRESHOLDS = {
    "2": {ENGLISH: 0.90, TYPED: 0.80, JEV: 0.90},
    "3+": {ENGLISH: 0.75, TYPED: 0.55, JEV: 0.90},
}

_COMPACT_KEYS = ("type", "choice", "score", "noul", "answer_confidence", "uncertain", "answered_by", "probabilities",
                 "also_check", "unknown", "candidates")
_ROUNDED = ("answer_confidence", "score", "noul")
_INTERNAL_KEYS = ("options", "voters")  # the service's hand-over to `combine`; never part of an answer


def compact(answer: dict[str, Any]) -> dict[str, Any]:
    """The part of an answer the caller needs to act on (see the module docstring)."""
    out = {key: answer[key] for key in _COMPACT_KEYS if key in answer}
    for key in _ROUNDED:
        if key in out:
            out[key] = round(out[key], 2)
    if "probabilities" in out:
        out["probabilities"] = {option: round(p, 2) for option, p in out["probabilities"].items()}
    return out


def _public(answer: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in answer.items() if k not in _INTERNAL_KEYS and v is not None}


def _key(name: str) -> str:
    """The threshold row of a voter: any fallback backend counts as Jev."""
    return name if name in (ENGLISH, TYPED) else JEV


class TriageFlow:
    """One request's worth of the flow; build a new one per request (it holds that request's state). `trace` True
    always returns the full answer, False the compact one; None follows the request and `classifier.triage_trace`."""

    def __init__(
        self, use_fallback: bool = True, thresholds: dict[str, dict[str, float]] | None = None,
        trace: bool | None = None, settings_snapshot=None, check=None, on_usage=None, partial_results=False,
        service: laya_agent.LAYAAgent | None = None,
    ) -> None:
        self.service = service or laya_agent.agent()
        self.config = settings_snapshot or decision.settings()
        self.check = check
        self.on_usage = on_usage
        self.partial_results = partial_results
        self.use_fallback = use_fallback
        self.trace = trace
        configured = self.config.triage_thresholds
        self.thresholds = {
            count: {**row, **configured.get(count, {}), **(thresholds or {}).get(count, {})}
            for count, row in DEFAULT_THRESHOLDS.items()
        }
        self.tokens = 0
        self._failures: list[str] = []
        self._override: float | None = None
        self._strategy: str | None = None

    def threshold(self, name: str, count: int) -> float:
        if self._override is not None:
            return self._override
        return self.thresholds["2" if count == 2 else "3+"][_key(name)]

    # -- asking ------------------------------------------------------------------------------------
    def _fallback_ready(self) -> bool:
        return self.use_fallback and decision.settings().triage_fallback and decision.available("triage", ("laya",))

    def _ask_jev(self, request: Request, qid: str) -> dict[str, Any] | None:
        answers, tokens, _ = laya_provider._ask_fallback(request, [qid])
        self.tokens += tokens
        return answers.get(qid)

    def _record(self, calls: list[dict[str, Any]], started_at: str) -> None:
        """The Laya service's model calls, into the token count and the caller's usage log."""
        for call in calls:
            tokens = call.get("input_tokens")
            if tokens is not None:
                self.tokens += tokens
            if self.on_usage:
                self.on_usage({"provider_id": "laya", "model": call["model"], "started_at": started_at,
                               "duration_ms": call["duration_ms"], "input_tokens": tokens,
                               "output_tokens": 0 if tokens is not None else None, "ok": bool(call["ok"]),
                               "reason": "" if call["ok"] else "local_failed"})

    def _ask_locals(self, request: Request) -> dict[str, dict[str, Any]]:
        """The service's answer per question id, one service call per strategy; a question it could not answer is left out."""
        config = decision.settings()
        groups: dict[str, dict[str, Any]] = {}
        for qid, spec in request.questions.items():
            if self._strategy:
                groups.setdefault(self._strategy, {})[qid] = spec
                continue
            local = tuple(v for v in config.voters(spec["type"]) if v != JEV)
            if local in _STRATEGIES:
                groups.setdefault(_STRATEGIES[local], {})[qid] = spec
        thresholds = {count: {n: v for n, v in row.items() if n != JEV} for count, row in self.thresholds.items()}
        answers: dict[str, dict[str, Any]] = {}
        for strategy, questions in groups.items():
            if self.check:
                self.check()
            started_at = datetime.now(timezone.utc).isoformat()
            try:
                result = self.service.ask(
                    strategy, request.text, questions, config.triage_window, min_confidence=self._override,
                    thresholds=thresholds, prune_ratio=config.triage_prune_ratio, pair_ratio=config.triage_pair_ratio,
                )
            except LayaServiceError as error:
                if error.status == 422:
                    raise ValueError(f"Invalid Laya request: {error}") from None
                _log.warning("Laya could not answer: %s", error)
                self._failures.append(f"laya: {error}")
                self._record(error.calls, started_at)
            else:
                self._record(result["calls"], started_at)
                answers.update(result["answers"])
            if self.check:
                self.check()
        return answers

    def _validate(self, request: Request) -> None:
        """The Laya service owns the question rules. If it cannot be reached the questions go unchecked and Jev may
        still answer; a malformed one then fails in `_settle` and is reported as a failed question."""
        try:
            self.service.validate(request.questions)
        except LayaServiceError as error:
            if error.status == 422:
                raise ValueError(f"Invalid Laya request: {error}") from None
            _log.warning("Laya questions could not be validated: %s", error)

        if self._strategy:
            try:
                names = self.service.strategies()["strategies"]
            except LayaServiceError as error:
                _log.warning("Laya strategies could not be listed: %s", error)
                return
            if self._strategy not in names:
                raise ValueError(f"Invalid Laya request: unknown strategy {self._strategy!r}; choose one of: {', '.join(names)}")

    def _no_answer(self, qid: str) -> str:
        """The error for a question nobody answered, with what the Laya service said when it failed."""
        return f"no model could answer {qid!r}" + (f" ({'; '.join(self._failures)})" if self._failures else "")

    # -- settling ----------------------------------------------------------------------------------
    def answer(self, raw: str) -> ChatResult:
        with decision.scoped_settings(self.config, self.on_usage, self.check):
            return self._answer(raw)

    def _answer(self, raw: str) -> ChatResult:
        # A longer text is refused outright unless Jev, with its larger window, may take it.
        limit = decision.settings().max_input_chars if self._fallback_ready() else laya_provider.MAX_INPUT_CHARS
        request = laya_provider.parse_request(raw, limit)
        self.use_fallback = self.use_fallback and not request.local_only
        data, _ = json.JSONDecoder().raw_decode(raw.lstrip())
        self._override = float(data["min_confidence"]) if "min_confidence" in data else None
        self.tokens, self._failures = 0, []
        self._strategy = request.strategy or tuning_overrides.triage_strategy()
        self._validate(request)
        local = self._ask_locals(request)
        answers = {}
        for qid, spec in request.questions.items():
            try:
                answers[qid] = self._settle(request, qid, spec, local.get(qid))
            except (ValueError, TypeError, KeyError, AttributeError):  # the last three: an unvalidated question (see _validate)
                if not self.partial_results:
                    raise
                answers[qid] = {"type": spec["type"], "choice": None, "uncertain": True,
                                "answer_confidence": 0, "answered_by": "", "probabilities": {}}
        beyond = sorted({
            part for a in answers.values() for part in str(a.get("answered_by", ENGLISH)).split("+") if part != ENGLISH
        })
        note = f"Settled with help from {', '.join(beyond)}." if beyond else ""
        full = self.trace if self.trace is not None else (request.trace or decision.settings().triage_trace)
        result = {
            "answers": answers if full else {qid: compact(a) for qid, a in answers.items()},
            "uncertain": any(a["uncertain"] for a in answers.values()),
        }
        return ChatResult(
            response=json.dumps(result), provider_id=laya_provider.PROVIDER_ID, model=laya_provider.DEFAULT_MODEL,
            input_tokens=self.tokens, output_tokens=0, total_tokens=self.tokens, context_tokens=None, model_note=note,
        )

    def _settle(self, request: Request, qid: str, spec: dict[str, Any], local: dict[str, Any] | None) -> dict[str, Any]:
        if local is not None and not local["uncertain"]:
            return _public(local)
        if not (JEV in decision.settings().voters(spec["type"]) and self._fallback_ready()):
            if local is None:
                raise ValueError(self._no_answer(qid))
            return _public(local)
        if spec["type"] == "choice":
            return self._settle_choice(request, qid, spec, local)
        jev = self._ask_jev(request, qid)
        if jev is None:
            if local is None:
                raise ValueError(self._no_answer(qid))
            return _public(local)
        count = 2 if spec["type"] == "noul" else 3
        return {**jev, "uncertain": jev["answer_confidence"] < self.threshold(JEV, count) - 1e-9}

    def _settle_choice(self, request: Request, qid: str, spec: dict[str, Any], local: dict[str, Any] | None) -> dict[str, Any]:
        """Steps 2 to 5 for a choice question the service left unsettled (or could not answer: `local` is None)."""
        config = decision.settings()
        options = list(local.get("options") or spec["criteria"]) if local else list(spec["criteria"])
        eliminated = list(local.get("eliminated", [])) if local else []
        rounds = list(local.get("rounds", [])) if local else []
        latest = dict(local.get("voters") or {local["answered_by"]: _public(local)}) if local else {}

        def ask() -> dict[str, Any] | None:
            narrowed = Request(request.text, {qid: {**spec, "criteria": {o: spec["criteria"][o] for o in options}}},
                               request.min_confidence)
            answer = self._ask_jev(narrowed, qid)
            if answer is None:
                rounds.append({"step": JEV, "failed": "could not answer", "options": list(options)})
                return None
            rounds.append({
                "step": JEV, "choice": answer["choice"], "confidence": answer["answer_confidence"],
                "probabilities": {o: round(p, 4) for o, p in answer["probabilities"].items()},
                **({"options": list(options)} if eliminated else {}), "threshold": self.threshold(JEV, len(options)),
            })
            latest[JEV] = answer
            return answer

        def sure(answer: dict[str, Any] | None) -> bool:
            return answer is not None and answer["answer_confidence"] >= self.threshold(JEV, len(options)) - 1e-9

        def decided(answer: dict[str, Any], resolved_by: str) -> dict[str, Any]:
            out = {**answer, "answered_by": JEV, "resolved_by": resolved_by, "uncertain": False, "rounds": rounds}
            return laya_provider._with_eliminated(spec, out, eliminated) if eliminated else out

        def mix() -> dict[str, Any] | None:
            try:
                return self.service.combine(latest, options, config.triage_prune_ratio, config.triage_pair_ratio)
            except LayaServiceError as error:
                self._failures.append(f"laya: {error}")
                return None

        jev = ask()
        if sure(jev):
            return decided(jev, "narrowed" if eliminated else "jev")
        if jev is None and local is not None:
            return _public(local)
        if jev is not None and len(options) > 2 and (mixed := mix()) is not None and len(mixed["kept"]) != len(options):
            gone = [o for o in options if o not in mixed["kept"]]
            eliminated.extend(gone)
            rounds.append({"step": "average", "probabilities": {o: round(p, 4) for o, p in mixed["average"].items()},
                           "eliminated": gone})
            options, latest = mixed["kept"], mixed["voters"]
            jev = ask()
            if sure(jev):
                return decided(jev, "narrowed")
        if not latest:
            raise ValueError(self._no_answer(qid))
        mixed = mix()
        if mixed is None or len(mixed["voters"]) == 1:  # Jev alone, or the service could not compare
            voters = mixed["voters"] if mixed else latest
            name = JEV if JEV in voters else next(iter(voters))
            answer = voters[name]
            out = {**answer, "answered_by": name, "uncertain": True, "rounds": rounds}
        else:
            out = {**mixed["final"], "rounds": rounds}
        return laya_provider._with_eliminated(spec, out, eliminated) if eliminated else out
