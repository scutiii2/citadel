"""The Triage Assistant's flow: Laya English, Laya typed-decisions and the fallback classifier (Jev)
as separate voters, each against its own confidence threshold.

Every request runs here (llm/laya_provider.py hands it over); `scripts/check_triage_cases.py --three-way` exercises the same code. Per `choice` question (the Laya models below are those `classifier.triage_order` / `triage_enabled` allow for choice,
in that order; English then typed is the default):

  1. Laya English answers. If its confidence meets its threshold, that is the answer.
  2. Otherwise Laya typed answers. If it picks the same option as English and meets its own threshold, that
     option is the answer (if English could not answer at all, a typed answer that meets its threshold stands).
  3. Same pick but both under their thresholds, or the two disagree:
     - With 3 or more options: average the two Laya models' probabilities, drop the options far below the best
       (under `triage_prune_ratio` of its value, never fewer than two left) and ask again over what is left,
       English first and then typed; the first one that meets its threshold decides. Repeat (at most 3 rounds)
       while options can still be dropped.
     - Then, with 2 options left or nothing more to drop, Jev is asked (if `triage_fallback` is on and a
       backend is available).
  4. If Jev meets its threshold, its answer is the answer. If not, the options are narrowed once more by the
     average of all the models, and Jev is asked again; if it now meets its threshold, that is the answer.
  5. Still undecided: for each remaining option N the models' values are compared in pairs,
     (|E-T| + |J-T| + |J-E|) / 3, where each value is the model's probability for N times its own confidence
     (with fewer models, the pairs there are). When the top option's value clearly leads (the next is under
     `triage_pair_ratio` of it) it is the answer and the other option(s) go in `also_check`; otherwise the
     answer is `unknown`, with the leading options as `candidates`.

Default thresholds (confidence 0-1, "at or above"; `classifier.triage_thresholds` changes any of them):
    2 options:   laya-english 0.90, laya-typed 0.80, jev 0.90
    3+ options:  laya-english 0.75, laya-typed 0.55, jev 0.90
A `min_confidence` in a request replaces all of them for that request. Score and noul questions are not
averaged: the first voter, in the configured order for that type (`classifier.triage_order`, `triage_enabled`), that meets
its threshold (3+ for score, 2 for noul) answers, else Jev's answer if it was asked, else the most confident local one.
By default a noul question skips English (its yes/no label bug), so typed, then Jev, answers it. Nothing leaves the
machine unless Jev is asked.

What is returned is compact by default, since the orchestrator reads it on every turn (a reviewed answer was
about 560 tokens with its trace, about 65 without): `type`, the pick (`choice`, `score` or `noul`), `answer_confidence`,
`uncertain`, `answered_by`, `probabilities` (2 decimals) and, when they apply, `also_check`, `unknown` and
`candidates`. The full answer adds `resolved_by`, `eliminated`, `disagreement`, `note`, a `legend` for score questions and
a `rounds` trace of every model call. Ask for it with `"trace": true` in a request, or set `classifier.triage_trace`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.llm import decision, laya_provider
from src.llm.base_provider import ChatResult
from src.llm.decision import TRIAGE_COUNTS, TRIAGE_VOTERS
from src.llm.laya_provider import LayaQuestions, Request

_log = logging.getLogger(__name__)

ENGLISH, TYPED, JEV = TRIAGE_VOTERS
CHECKPOINTS = {ENGLISH: laya_provider.DEFAULT_MODEL, TYPED: "typed-decisions"}
MAX_NARROWING = 3
DEFAULT_THRESHOLDS = {
    "2": {ENGLISH: 0.90, TYPED: 0.80, JEV: 0.90},
    "3+": {ENGLISH: 0.75, TYPED: 0.55, JEV: 0.90},
}


_COMPACT_KEYS = ("type", "choice", "score", "noul", "answer_confidence", "uncertain", "answered_by", "probabilities",
                 "also_check", "unknown", "candidates")
_ROUNDED = ("answer_confidence", "score", "noul")


def compact(answer: dict[str, Any]) -> dict[str, Any]:
    """The part of an answer the caller needs to act on (see the module docstring)."""
    out = {key: answer[key] for key in _COMPACT_KEYS if key in answer}
    for key in _ROUNDED:
        if key in out:
            out[key] = round(out[key], 2)
    if "probabilities" in out:
        out["probabilities"] = {option: round(p, 2) for option, p in out["probabilities"].items()}
    return out


def parse_threshold(text: str) -> tuple[str, str, float]:
    """`laya-typed:3+=0.6` -> ("laya-typed", "3+", 0.6)."""
    try:
        left, value = text.split("=")
        name, count = left.split(":")
        number = float(value)
    except ValueError as error:
        raise SystemExit(f"--threshold wants MODEL:COUNT=VALUE, for example laya-typed:3+=0.6 (got {text!r})") from error
    if name not in TRIAGE_VOTERS or count not in TRIAGE_COUNTS or not 0 < number <= 1:
        raise SystemExit(f"--threshold {text!r}: MODEL is one of {', '.join(TRIAGE_VOTERS)}; COUNT is 2 or 3+; VALUE is 0-1")
    return name, count, number


def _key(name: str) -> str:
    """The threshold row of a voter: any fallback backend counts as Jev."""
    return name if name in (ENGLISH, TYPED) else JEV


def _rounded(values: dict[str, float]) -> dict[str, float]:
    return {name: round(value, 4) for name, value in values.items()}


def _mean(answers: dict[str, dict[str, Any]]) -> dict[str, float]:
    options = list(next(iter(answers.values()))["probabilities"])
    return {o: sum(a["probabilities"][o] for a in answers.values()) / len(answers) for o in options}


def _restrict(answer: dict[str, Any], options: list[str]) -> dict[str, Any]:
    """The answer's probabilities over only `options`, renormalised (a model answered before options were dropped)."""
    kept = {o: answer["probabilities"].get(o, 0.0) for o in options}
    total = sum(kept.values())
    return {**answer, "probabilities": {o: (v / total if total else 1 / len(options)) for o, v in kept.items()}}


def final_answer(voters: dict[str, dict[str, Any]], rounds: list[dict[str, Any]]) -> dict[str, Any]:
    """Step 5: pairwise differences of the confidence-weighted values, per option."""
    options = list(next(iter(voters.values()))["probabilities"])
    scaled = {name: {o: a["answer_confidence"] * a["probabilities"][o] for o in options} for name, a in voters.items()}
    names = list(scaled)
    pairs = [(x, y) for i, x in enumerate(names) for y in names[i + 1:]]
    score = {o: sum(abs(scaled[x][o] - scaled[y][o]) for x, y in pairs) / len(pairs) for o in options}
    # A tie goes to the pick of the most confident voter.
    leader = max(voters.values(), key=lambda a: a["answer_confidence"])["choice"]
    ranked = sorted(options, key=lambda o: (round(score[o], 6), o == leader), reverse=True)
    top, runner_up = ranked[0], ranked[1]
    decided = score[top] > 0 and score[runner_up] < decision.settings().triage_pair_ratio * score[top]
    total = sum(score.values())
    share = {o: (score[o] / total if total else 1 / len(options)) for o in options}
    rounds += [{"step": f"{name} x confidence", "options": options, "probabilities": _rounded(v)} for name, v in scaled.items()]
    rounds.append({
        "step": "difference", "options": options, "probabilities": _rounded(score),
        "choice": top if decided else "unknown: " + " or ".join(ranked[:2]),
    })
    who = " and ".join(names)
    out: dict[str, Any] = {
        "type": "choice", "choice": top, "probabilities": _rounded(share), "answer_confidence": round(share[top], 4),
        "uncertain": not decided, "answered_by": "+".join(names), "resolved_by": "final",
        "disagreement": {name: a["choice"] for name, a in voters.items()}, "also_check": ranked[1:3],
    }
    if decided:
        out["note"] = f"{who} did not settle it; {top} stands out most, but also check {' and '.join(ranked[1:3])}."
    else:
        out["unknown"] = True
        out["candidates"] = ranked[:2]
        out["note"] = f"The answer is unknown: it could be {' or '.join(ranked[:2])}; check both."
    return out


class TriageFlow:
    """One request's worth of the flow. `locals_` maps "laya-english" and "laya-typed" to a
    LayaQuestions each; build a new one per request (it holds that request's state). `trace` True always returns the
    full answer, False the compact one; None follows the request and `classifier.triage_trace`."""

    def __init__(
        self, locals_: dict[str, LayaQuestions], use_fallback: bool = True,
        thresholds: dict[str, dict[str, float]] | None = None, trace: bool | None = None,
    ) -> None:
        self.locals = locals_
        self.use_fallback = use_fallback
        self.trace = trace
        configured = decision.settings().triage_thresholds
        self.thresholds = {
            count: {**row, **configured.get(count, {}), **(thresholds or {}).get(count, {})}
            for count, row in DEFAULT_THRESHOLDS.items()
        }
        self.tokens = 0
        self._request: Request | None = None
        self._override: float | None = None
        self._cache: dict[str, dict[str, dict[str, Any]] | None] = {}

    def threshold(self, name: str, count: int) -> float:
        if self._override is not None:
            return self._override
        return self.thresholds["2" if count == 2 else "3+"][_key(name)]

    # -- asking ------------------------------------------------------------------------------------
    def _fallback_ready(self) -> bool:
        return self.use_fallback and decision.settings().triage_fallback and decision.available("triage", ("laya",))

    def _run_local(self, name: str, request: Request) -> dict[str, dict[str, Any]] | None:
        try:
            answers, tokens = self.locals[name]._laya_answers(request)
        except (ValueError, RuntimeError) as error:
            _log.warning("%s could not answer: %s", name, error)
            return None
        self.tokens += tokens
        return answers

    def _ask_voter(self, name: str, request: Request, qid: str) -> dict[str, Any] | None:
        """One voter's answer to one question of `request`; the whole original request is asked once per model."""
        if name == JEV:
            answers, tokens, _ = laya_provider._ask_fallback(request, [qid])
            self.tokens += tokens
            return answers.get(qid)
        if request is self._request:
            if name not in self._cache:
                self._cache[name] = self._run_local(name, request)
            answers = self._cache[name]
        else:
            answers = self._run_local(name, request)
        return None if answers is None else answers[qid]

    # -- settling ----------------------------------------------------------------------------------
    def answer(self, raw: str) -> ChatResult:
        # A longer text is refused outright unless Jev, with its larger window, may take it.
        limit = decision.settings().max_input_chars if self._fallback_ready() else laya_provider.MAX_INPUT_CHARS
        request = laya_provider.parse_request(raw, limit)
        data, _ = json.JSONDecoder().raw_decode(raw.lstrip())
        self._override = float(data["min_confidence"]) if "min_confidence" in data else None
        self._request, self._cache, self.tokens = request, {}, 0
        answers = {}
        for qid, spec in request.questions.items():
            settle = self._settle_choice if spec["type"] == "choice" else self._settle_other
            answers[qid] = settle(request, qid, spec)
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

    def _settle_choice(self, request: Request, qid: str, spec: dict[str, Any]) -> dict[str, Any]:
        rounds: list[dict[str, Any]] = []
        eliminated: list[str] = []
        options = list(spec["criteria"])
        current = request
        latest: dict[str, dict[str, Any]] = {}

        def needs(name: str) -> float:
            return self.threshold(name, len(options))

        def ask(name: str) -> dict[str, Any] | None:
            answer = self._ask_voter(name, current, qid)
            narrowed = {"options": list(options)} if eliminated else {}
            if answer is None:
                rounds.append({"step": name, "failed": "could not answer", **narrowed})
                return None
            rounds.append({**laya_provider._round(name, answer, options if eliminated else None), "threshold": needs(name)})
            latest[name] = answer
            return answer

        def sure(name: str, answer: dict[str, Any] | None) -> bool:
            return answer is not None and answer["answer_confidence"] >= needs(name) - 1e-9

        def decided(answer: dict[str, Any], by: str, resolved_by: str) -> dict[str, Any]:
            out = {**answer, "answered_by": by, "resolved_by": resolved_by, "uncertain": False}
            if len(rounds) > 1 or eliminated:
                out["rounds"] = rounds
            return laya_provider._with_eliminated(spec, out, eliminated) if eliminated else out

        def narrow(average: dict[str, float]) -> bool:
            """Drop the options far below the best; True when any went."""
            nonlocal options, current
            ratio = decision.settings().triage_prune_ratio
            kept = laya_provider._kept_options(average, ratio) if ratio > 0 else list(average)
            if len(kept) == len(options):
                return False
            gone = [o for o in options if o not in kept]
            eliminated.extend(gone)
            rounds.append(laya_provider._average_round(average, gone))
            options = kept
            current = Request(
                request.text, {qid: {**spec, "criteria": {o: spec["criteria"][o] for o in kept}}}, request.min_confidence,
            )
            return True

        # 1 and 2: the local models in their configured order. The first sure one decides; a later one decides only
        # if it picks what the one before it did (or the one before could not answer).
        locals_here = [name for name in decision.settings().voters("choice") if name != JEV]
        before: tuple[str, dict[str, Any]] | None = None
        for name in locals_here:
            answer = ask(name)
            if sure(name, answer):
                if before is None:
                    return decided(answer, name, "local")
                if answer["choice"] == before[1]["choice"]:
                    return decided(answer, f"{before[0]}+{name}", "local")
            if answer is not None:
                before = (name, answer)

        # 3: with 3 or more options, drop the clearly worse ones and ask the local models again
        for _ in range(MAX_NARROWING):
            voters = {n: a for n, a in latest.items() if n in locals_here}
            if len(options) <= 2 or not voters or not narrow(_mean(voters)):
                break
            latest = {}
            for name in locals_here:
                answer = ask(name)
                if sure(name, answer):
                    return decided(answer, name, "narrowed")

        # 4: Jev, then Jev again over a narrower set
        if JEV in decision.settings().voters("choice") and self._fallback_ready():
            jev = ask(JEV)
            if sure(JEV, jev):
                return decided(jev, JEV, "narrowed" if eliminated else "jev")
            if jev is not None and len(options) > 2 and narrow(_mean(latest)):
                jev = ask(JEV)
                if sure(JEV, jev):
                    return decided(jev, JEV, "narrowed")

        # 5: nobody was sure: compare what they said
        voters = {n: _restrict(a, options) for n, a in latest.items()}
        if not voters:
            raise ValueError(f"no model could answer {qid!r}")
        if len(voters) == 1:
            name, answer = next(iter(voters.items()))
            out = {**answer, "answered_by": name, "uncertain": True, "rounds": rounds}
            return laya_provider._with_eliminated(spec, out, eliminated) if eliminated else out
        final = final_answer(voters, rounds)
        final["rounds"] = rounds
        return laya_provider._with_eliminated(spec, final, eliminated) if eliminated else final

    def _settle_other(self, request: Request, qid: str, spec: dict[str, Any]) -> dict[str, Any]:
        """Score and noul questions: the voters of that type in their configured order (`classifier.triage_order`);
        the first one that meets its threshold answers (3+ for a score question, the 2-option one for a noul question,
        which has two answers). Jev, when asked and unsure, still gives the answer, flagged by its own threshold."""
        count = 2 if spec["type"] == "noul" else 3
        best: tuple[str, dict[str, Any]] | None = None
        jev: dict[str, Any] | None = None
        for name in decision.settings().voters(spec["type"]):
            if name == JEV and not self._fallback_ready():
                continue
            answer = self._ask_voter(name, request, qid)
            if answer is None:
                continue
            if answer["answer_confidence"] >= self.threshold(name, count) - 1e-9:
                if name == JEV:
                    return {**answer, "uncertain": False}
                return {**answer, "answered_by": name, "resolved_by": "local", "uncertain": False}
            if name == JEV:
                jev = {**answer, "uncertain": True}
            elif best is None or answer["answer_confidence"] > best[1]["answer_confidence"]:
                best = (name, answer)
        if jev is not None:
            return jev
        if best is None:
            raise ValueError(f"no model could answer {qid!r}")
        return {**best[1], "answered_by": best[0], "uncertain": True}
