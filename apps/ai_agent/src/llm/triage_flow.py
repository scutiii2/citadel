"""The Triage Assistant's sequential flow: Laya English, Laya typed-decisions and the fallback classifier (Jev)
as separate voters, each against its own confidence threshold.

It runs when config_tuning.json's `classifier.triage_flow` is "sequential" (llm/laya_provider.py hands the
request here); `scripts/check_triage_cases.py --three-way` exercises the same code. Per `choice` question:

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
averaged: the first of English, typed, Jev that meets its 3+ threshold answers, else the most confident local
one. Each answer carries `answered_by`, `resolved_by` and, when more than one model was consulted, a `rounds`
trace of every model call. Nothing leaves the machine unless Jev is asked.
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
    """One request's worth of the sequential flow. `locals_` maps "laya-english" and "laya-typed" to a
    LayaQuestions each; build a new one per request (it holds that request's state)."""

    def __init__(
        self, locals_: dict[str, LayaQuestions], use_fallback: bool = True,
        thresholds: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self.locals = locals_
        self.use_fallback = use_fallback
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
        request = laya_provider.parse_request(raw, decision.settings().max_input_chars)
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
        result = {"answers": answers, "uncertain": any(a["uncertain"] for a in answers.values())}
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

        # 1 and 2: the two local models, English first
        english = ask(ENGLISH)
        if sure(ENGLISH, english):
            return decided(english, ENGLISH, "local")
        typed = ask(TYPED)
        if sure(TYPED, typed) and (english is None or typed["choice"] == english["choice"]):
            return decided(typed, f"{ENGLISH}+{TYPED}" if english else TYPED, "local")

        # 3: with 3 or more options, drop the clearly worse ones and ask the local models again
        for _ in range(MAX_NARROWING):
            voters = {n: a for n, a in latest.items() if n in (ENGLISH, TYPED)}
            if len(options) <= 2 or not voters or not narrow(_mean(voters)):
                break
            latest = {}
            english = ask(ENGLISH)
            if sure(ENGLISH, english):
                return decided(english, ENGLISH, "narrowed")
            typed = ask(TYPED)
            if sure(TYPED, typed):
                return decided(typed, TYPED, "narrowed")

        # 4: Jev, then Jev again over a narrower set
        if self._fallback_ready():
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
        """Score and noul questions: the first model that meets its 3+ threshold answers."""
        best: tuple[str, dict[str, Any]] | None = None
        for name in (ENGLISH, TYPED):
            answer = self._ask_voter(name, request, qid)
            if answer is None:
                continue
            if answer["answer_confidence"] >= self.threshold(name, 3) - 1e-9:
                return {**answer, "answered_by": name, "resolved_by": "local", "uncertain": False}
            if best is None or answer["answer_confidence"] > best[1]["answer_confidence"]:
                best = (name, answer)
        if self._fallback_ready():
            answer = self._ask_voter(JEV, request, qid)
            if answer is not None:
                answer["uncertain"] = answer["answer_confidence"] < self.threshold(JEV, 3)
                return answer
        if best is None:
            raise ValueError(f"no model could answer {qid!r}")
        return {**best[1], "answered_by": best[0], "uncertain": True}
