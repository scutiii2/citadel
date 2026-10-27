"""Runs a decision strategy over the gateway arrangement [laya, jev].

laya-only / jev-only ask one gateway. `both` asks laya first and jev only about the questions laya failed
to settle (error, or confidence below the request's minimum). The agent wrapper picks the strategy; gateways
never chain among themselves."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import anyio.to_thread

from src.providers.decision.contract import DecisionError, DecisionGateway, DecisionRequest

STRATEGIES = ("laya-only", "jev-only", "both")
ARRANGEMENT = ("laya", "jev")
_ORDER = {"laya-only": ("laya",), "jev-only": ("jev",), "both": ARRANGEMENT}
_EPSILON = 1e-9


@dataclass(frozen=True)
class DecisionResult:
    answers: dict[str, dict[str, Any]]
    tokens: int
    unsettled: tuple[str, ...]


@dataclass(frozen=True)
class Choice:
    choice: str
    confidence: int
    prompt_tokens: int
    backend: str
    model: str
    probabilities: dict[str, float] | None = None


def default_gateways() -> dict[str, DecisionGateway]:
    from src.providers.decision.gateways.jev import JevGateway
    from src.providers.decision.gateways.laya import LayaGateway

    return {"laya": LayaGateway(), "jev": JevGateway()}


def _settled(answer: Mapping[str, Any] | None, minimum: float) -> bool:
    return (answer is not None and not answer.get("uncertain", True) and not answer.get("unknown")
            and answer.get("answer_confidence", 0) >= minimum - _EPSILON)


def run(strategy: str, request: DecisionRequest, *, gateways: Mapping[str, DecisionGateway] | None = None,
        on_usage: Callable[[dict[str, Any]], None] | None = None,
        check: Callable[[], float] | None = None) -> DecisionResult:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown decision strategy {strategy!r}; choose one of: {', '.join(STRATEGIES)}")
    gateways = gateways if gateways is not None else default_gateways()
    effective_strategy = "laya-only" if request.local_only else strategy
    names = [n for n in _ORDER[effective_strategy] if not (request.local_only and not gateways[n].local)]
    pending = dict(request.questions)
    answers: dict[str, dict[str, Any]] = {}
    tokens = 0
    problems: list[str] = []
    for name in names:
        if not pending:
            break
        gateway = gateways[name]
        if not gateway.available():
            problems.append(f"{name} is not available")
            continue
        limit = check() if check else None
        started, started_at = time.monotonic(), datetime.now(timezone.utc).isoformat()
        result = None
        try:
            result = gateway.ask(replace(request, questions=pending), limit)
        except DecisionError as error:
            problems.append(f"{name}: {error}")
        finally:
            if on_usage:
                on_usage({"provider_id": name, "model": result.model if result else name, "started_at": started_at,
                          "duration_ms": round((time.monotonic() - started) * 1000),
                          "input_tokens": result.tokens if result else None,
                          "output_tokens": 0 if result else None, "ok": result is not None,
                          "reason": "" if result else "backend_failed"})
        if result is None:
            continue
        tokens += result.tokens
        for qid, answer in result.answers.items():
            answers[qid] = {**answer, "answered_by": name}
        pending = {q: s for q, s in pending.items() if not _settled(answers.get(q), request.min_confidence)}
    if not answers:
        raise DecisionError("; ".join(problems) or "no decision gateway could be asked")
    for qid in pending:
        if qid in answers:
            answers[qid]["uncertain"] = True
    return DecisionResult(answers, tokens, tuple(q for q in pending if q in answers))


async def arun(strategy: str, request: DecisionRequest, **kwargs: Any) -> DecisionResult:
    return await anyio.to_thread.run_sync(lambda: run(strategy, request, **kwargs))


def ask_choice(subject: str, criteria: Mapping[str, str], question: str, *, strategy: str, min_confidence: int,
               gateways: Mapping[str, DecisionGateway] | None = None,
               on_usage: Callable[[dict[str, Any]], None] | None = None, timeout: float | None = None) -> Choice:
    """One choice question: the answer with its confidence in percent (0-100)."""
    if len(criteria) < 2:
        raise DecisionError("a choice needs at least two options")
    request = DecisionRequest(subject, {"answer": {"type": "choice", "instructions": question, "criteria": dict(criteria)}},
                              min_confidence=min_confidence / 100)
    result = run(strategy, request, gateways=gateways, on_usage=on_usage,
                 check=(lambda: timeout) if timeout else None)
    answer = result.answers["answer"]
    return Choice(answer["choice"], round(answer["answer_confidence"] * 100), result.tokens, answer["answered_by"],
                  answer["answered_by"], answer.get("probabilities"))
