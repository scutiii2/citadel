"""A stand-in for LAYAAgent (the Laya service client): scripted `ask` results, one per call, and a scripted `combine`.

The decision rules themselves are the service's and are tested there (LayaAgent/tests); these tests cover what
Garrison does with the service's answers."""

from __future__ import annotations

import copy
from typing import Any, Callable

from src.llm.laya_agent import LayaServiceError


def spread(choice: str, confidence: float, options: list[str]) -> dict[str, float]:
    rest = (1 - confidence) / max(len(options) - 1, 1)
    return {o: (confidence if o == choice else rest) for o in options}


def choice(pick: str, confidence: float, options=("a", "b", "c"), uncertain: bool | None = None,
           by: str = "laya-english", **extra: Any) -> dict[str, Any]:
    """One choice answer as the service returns it (`uncertain` defaults to a confidence under 0.75)."""
    options = list(options)
    return {"type": "choice", "choice": pick, "answer_confidence": confidence,
            "probabilities": spread(pick, confidence, options),
            "uncertain": confidence < 0.75 if uncertain is None else uncertain, "answered_by": by, **extra}


def unsure(pick: str, confidence: float, options=("a", "b", "c"), voters: dict[str, Any] | None = None,
           **extra: Any) -> dict[str, Any]:
    """A choice the service could not settle: it hands over `options` and the models' latest `voters`."""
    answer = choice(pick, confidence, options, uncertain=True, **extra)
    return {**answer, "options": list(options), "voters": voters or {answer["answered_by"]: choice(pick, confidence, options)}}


def result(*answers: tuple[str, dict[str, Any]], tokens: int = 10, ok: bool = True) -> dict[str, Any]:
    """A service response: (question id, answer) pairs and one model call that read `tokens`."""
    answers_by_id = dict(answers)
    return {"strategy": "x", "answers": answers_by_id, "uncertain": any(a["uncertain"] for a in answers_by_id.values()),
            "calls": [{"model": "convaiinnovations/laya", "input_tokens": tokens, "duration_ms": 1, "ok": ok}]}


class FakeService:
    """`results` are returned by `ask` in order (an Exception is raised, a callable is called with the request).
    `mixed` is what `combine` returns: a dict, or a callable of (voters, options)."""

    def __init__(self, *results: Any, mixed: Any = None, invalid: str = "") -> None:
        self.results, self.mixed, self.invalid = list(results), mixed, invalid
        self.asked: list[dict[str, Any]] = []
        self.combined: list[dict[str, Any]] = []

    def ask(self, strategy, text, questions, max_len, **tuning):
        self.asked.append({"strategy": strategy, "text": text, "questions": copy.deepcopy(questions),
                           "max_len": max_len, **tuning})
        outcome = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if callable(outcome):
            outcome = outcome(self.asked[-1])
        if isinstance(outcome, Exception):
            raise outcome
        return copy.deepcopy(outcome)

    def combine(self, voters, options, prune_ratio, pair_ratio):
        self.combined.append({"voters": voters, "options": list(options), "prune_ratio": prune_ratio, "pair_ratio": pair_ratio})
        outcome = self.mixed(voters, options) if callable(self.mixed) else self.mixed
        if isinstance(outcome, Exception):
            raise outcome
        if outcome is None:
            raise LayaServiceError("combine was not scripted")
        return copy.deepcopy(outcome)

    def validate(self, questions):
        if self.invalid:
            raise LayaServiceError(self.invalid, status=422)

    def health(self) -> bool:
        return True

    configured = True
