"""Experimental triage where every model is its own voter: Laya (English), Laya (typed-decisions) and the
fallback classifier (Jev). Used by `check_triage_cases --three-way`; the Triage Assistant itself is unchanged.

It is the two-model review (llm/laya_provider.py) generalised to any number of voters, in the same order:

  0. Both Laya models answer locally. If they pick the same option and the more confident of them is at or
     above the request's min_confidence, that is the answer (`resolved_by: local`) and nothing is sent out.
     Otherwise the fallback is asked too (when classifier.triage_fallback is on and a backend is available).
  1. Confidence gap: if the most confident voter leads the next one by at least `triage_confidence_gap`,
     its answer stands as it is (`deferred_to`).
  2. Average and drop: the probabilities of all voters are averaged and options under `triage_prune_ratio`
     of the leader's average are dropped (never fewer than two stay). The question is asked again over what
     is left, voter by voter in order (Laya English, Laya typed, then the fallback), and the first voter that
     is sure decides. With nothing to drop the voters are blended instead.
  3. Pair rule: two options left and the voters still disagree. Each voter's probabilities are multiplied by
     its own confidence; per option the spread (largest minus smallest value across voters) is taken; if the
     smaller spread is under `triage_pair_ratio` of the larger one, the option with the bigger spread is the
     answer, otherwise it is unsure and both options are `candidates`. `also_check` names the other option.

Blending (nothing dropped, voters still unsure): the average distribution, the highest confidence when all
agree and the lowest when they do not (then `uncertain` is true and `disagreement` says who picked what).
Score and noul questions are not averaged: the first sure local answer, else the fallback's, else the most
confident local one. With the fallback off, only the two Laya models vote. The thresholds are the
`classifier` section of configs/config_tuning.json, as for the real triage.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

from src.llm import decision, laya_provider
from src.llm.laya_provider import LayaQuestions, Request

_log = logging.getLogger(__name__)

ENGLISH = "laya-english"
TYPED = "laya-typed"
CHECKPOINTS = {ENGLISH: "convaiinnovations/laya", TYPED: "typed-decisions"}


def _rounded(values: dict[str, float]) -> dict[str, float]:
    return {name: round(value, 4) for name, value in values.items()}


def _mean(answers: dict[str, dict[str, Any]]) -> dict[str, float]:
    options = list(next(iter(answers.values()))["probabilities"])
    return {o: sum(a["probabilities"][o] for a in answers.values()) / len(answers) for o in options}


def _leader(answers: dict[str, dict[str, Any]]) -> str:
    """The pick of the most confident voter (the first of equals)."""
    return max(answers.values(), key=lambda a: a["answer_confidence"])["choice"]


def _blend(request: Request, answers: dict[str, dict[str, Any]], rounds: list[dict[str, Any]]) -> dict[str, Any]:
    average = _mean(answers)
    unanimous = len({a["choice"] for a in answers.values()}) == 1
    confidences = [a["answer_confidence"] for a in answers.values()]
    confidence = max(confidences) if unanimous else min(confidences)
    leader = _leader(answers)
    rounds.append(laya_provider._average_round(average))
    out: dict[str, Any] = {
        "type": "choice", "choice": max(average, key=lambda o: (round(average[o], 6), o == leader)),
        "probabilities": _rounded(average), "answer_confidence": confidence,
        "uncertain": not unanimous or confidence < request.min_confidence,
        "answered_by": "+".join(answers), "resolved_by": "blend",
    }
    if not unanimous:
        out["disagreement"] = {name: a["choice"] for name, a in answers.items()}
    return out


def _pair(request: Request, answers: dict[str, dict[str, Any]], rounds: list[dict[str, Any]]) -> dict[str, Any]:
    options = list(next(iter(answers.values()))["probabilities"])
    scaled = {name: {o: a["answer_confidence"] * a["probabilities"][o] for o in options} for name, a in answers.items()}
    spread = {o: max(s[o] for s in scaled.values()) - min(s[o] for s in scaled.values()) for o in options}
    larger, smaller = max(spread.values()), min(spread.values())
    decided = larger > 0 and smaller < decision.settings().triage_pair_ratio * larger
    total = sum(spread.values())
    share = {o: (spread[o] / total if total else 1 / len(options)) for o in options}
    leader = _leader(answers)
    choice = max(options, key=lambda o: (round(spread[o], 6), o == leader))
    rounds += [
        {"step": f"{name} x confidence", "options": options, "probabilities": _rounded(values)} for name, values in scaled.items()
    ]
    rounds.append({
        "step": "difference", "options": options, "probabilities": _rounded(spread),
        "choice": choice if decided else "unsure: " + " or ".join(options),
    })
    who = " and ".join(answers)
    other = [o for o in options if o != choice]
    out: dict[str, Any] = {
        "type": "choice", "choice": choice, "probabilities": _rounded(share), "answer_confidence": round(share[choice], 4),
        "uncertain": not decided, "answered_by": "+".join(answers), "resolved_by": "pair",
        "disagreement": {name: a["choice"] for name, a in answers.items()}, "also_check": other,
    }
    if decided:
        out["note"] = f"{who} disagreed; {choice} is the stronger answer, but also check {' and '.join(other)}."
    else:
        out["candidates"] = options
        out["note"] = f"{who} disagreed and the weighed answers are too close to call: it could be {' or '.join(options)}; check both."
    return out


def settled_locally(votes: dict[str, dict[str, Any]], min_confidence: float) -> bool:
    """All local voters pick the same option and the most confident of them is sure."""
    picks = {a["choice"] for a in votes.values()}
    return bool(votes) and len(picks) == 1 and max(a["answer_confidence"] for a in votes.values()) >= min_confidence - 1e-9


def local_answer(votes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rounds = [laya_provider._round(name, a) for name, a in votes.items()]
    if len(votes) == 1:
        name, answer = next(iter(votes.items()))
        return {**answer, "answered_by": name, "resolved_by": "local"}
    average = _mean(votes)
    rounds.append(laya_provider._average_round(average))
    leader = _leader(votes)
    return {
        "type": "choice", "choice": max(average, key=lambda o: (round(average[o], 6), o == leader)),
        "probabilities": _rounded(average), "answer_confidence": max(a["answer_confidence"] for a in votes.values()),
        "uncertain": False, "answered_by": "+".join(votes), "resolved_by": "local", "rounds": rounds,
    }


class ThreeWayTriage:
    """Drop-in for LayaQuestions in check_triage_cases: `answer(raw)` returns an object with `response` and
    `input_tokens`."""

    def __init__(self, locals_: dict[str, LayaQuestions], use_fallback: bool = True) -> None:
        self.locals = locals_
        self.use_fallback = use_fallback
        self.tokens = 0

    @classmethod
    def load(cls, max_len: int, use_fallback: bool = True) -> "ThreeWayTriage":
        import laya

        laya_provider.CONTEXT_WINDOW = max_len
        laya_provider.MAX_INPUT_CHARS = 200_000
        return cls({name: LayaQuestions(laya.load(model)) for name, model in CHECKPOINTS.items()}, use_fallback)

    def prepare(self) -> None:
        for questions in self.locals.values():
            questions.prepare()

    # -- asking ------------------------------------------------------------------------------------
    def _fallback_ready(self) -> bool:
        return self.use_fallback and decision.settings().triage_fallback and decision.available("triage", ("laya",))

    def _ask_remote(self, request: Request, qid: str) -> dict[str, Any] | None:
        answers, tokens, _ = laya_provider._ask_fallback(request, [qid])
        self.tokens += tokens
        return answers.get(qid)

    def _ask_voter(self, name: str, request: Request, qid: str) -> dict[str, Any] | None:
        """One voter's answer to one question of `request` (None when it could not answer)."""
        if name in self.locals:
            try:
                answers, tokens = self.locals[name]._laya_answers(request)
            except (ValueError, RuntimeError) as error:
                _log.warning("%s could not answer %r: %s", name, qid, error)
                return None
            self.tokens += tokens
            return answers[qid]
        return self._ask_remote(request, qid)

    # -- settling ----------------------------------------------------------------------------------
    def answer(self, raw: str) -> Any:
        request = laya_provider.parse_request(raw, laya_provider.MAX_INPUT_CHARS)
        self.tokens = 0
        local: dict[str, dict[str, dict[str, Any]]] = {}
        for name, questions in self.locals.items():
            try:
                answers, tokens = questions._laya_answers(request)
            except (ValueError, RuntimeError) as error:
                _log.warning("%s could not read the request: %s", name, error)
                continue
            local[name] = answers
            self.tokens += tokens
        out = {}
        for qid, spec in request.questions.items():
            votes = {name: answers[qid] for name, answers in local.items()}
            out[qid] = self._settle(request, qid, spec, votes)
        return SimpleNamespace(response=json.dumps({"answers": out}), input_tokens=self.tokens)

    def _settle(self, request: Request, qid: str, spec: dict[str, Any], votes: dict[str, dict[str, Any]]) -> dict[str, Any]:
        if spec["type"] != "choice":
            return self._settle_other(request, qid, votes)
        if settled_locally(votes, request.min_confidence):
            return local_answer(votes)
        if self._fallback_ready():
            remote = self._ask_remote(request, qid)
            if remote is not None:
                votes = {**votes, remote["answered_by"]: remote}
        if not votes:
            raise ValueError(f"no model could answer {qid!r}")
        if len(votes) == 1:
            name, answer = next(iter(votes.items()))
            return {**answer, "answered_by": name, "resolved_by": "alone"}
        return self._review(request, qid, spec, votes)

    def _settle_other(self, request: Request, qid: str, votes: dict[str, dict[str, Any]]) -> dict[str, Any]:
        for name, answer in votes.items():
            if not answer["uncertain"]:
                return {**answer, "answered_by": name, "resolved_by": "local"}
        if self._fallback_ready():
            remote = self._ask_remote(request, qid)
            if remote is not None:
                return remote
        if not votes:
            raise ValueError(f"no model could answer {qid!r}")
        name, answer = max(votes.items(), key=lambda kv: kv[1]["answer_confidence"])
        return {**answer, "answered_by": name}

    def _review(self, request: Request, qid: str, spec: dict[str, Any], votes: dict[str, dict[str, Any]]) -> dict[str, Any]:
        settings = decision.settings()
        rounds = [laya_provider._round(name, answer) for name, answer in votes.items()]
        ranked = sorted(votes.items(), key=lambda kv: kv[1]["answer_confidence"], reverse=True)
        gap = ranked[0][1]["answer_confidence"] - ranked[1][1]["answer_confidence"]
        if gap >= settings.triage_confidence_gap - 1e-9:
            name, answer = ranked[0]
            rounds.append({"step": "gap", "gap": round(gap, 4), "deferred_to": name})
            return {**answer, "answered_by": name, "deferred_to": name, "resolved_by": "gap", "rounds": rounds}
        average = _mean(votes)
        ratio = settings.triage_prune_ratio
        kept = laya_provider._kept_options(average, ratio) if ratio > 0 else list(average)
        if len(kept) == len(average):
            disagree = len({a["choice"] for a in votes.values()}) > 1
            out = _pair(request, votes, rounds) if len(average) == 2 and disagree else _blend(request, votes, rounds)
            return {**out, "rounds": rounds}
        eliminated = [name for name in average if name not in kept]
        rounds.append(laya_provider._average_round(average, eliminated))
        narrowed = Request(request.text, {qid: {**spec, "criteria": {o: spec["criteria"][o] for o in kept}}}, request.min_confidence)
        asked: dict[str, dict[str, Any]] = {}
        for name in votes:
            answer = self._ask_voter(name, narrowed, qid)
            if answer is None:
                rounds.append({"step": name, "options": kept, "failed": "could not answer"})
                continue
            asked[name] = answer
            rounds.append(laya_provider._round(name, answer, kept))
            if not answer["uncertain"]:
                break
        if not asked:
            return {**_blend(request, votes, rounds), "rounds": rounds}
        name, last = list(asked.items())[-1]
        if not last["uncertain"] or len(asked) == 1:
            final = {**last, "answered_by": name}
        elif len(kept) == 2 and len({a["choice"] for a in asked.values()}) > 1:
            final = _pair(request, asked, rounds)
        else:
            final = _blend(request, asked, rounds)
        return {**laya_provider._with_eliminated(spec, final, eliminated), "rounds": rounds}
