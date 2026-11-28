"""Asks an ordered list of saved decision gateways.

The list is the agent's own (llm.gateway, then llm.fallback_gateways). The next gateway is asked only about the
questions the ones before it failed to settle (error, or confidence below the request's minimum); gateways never
chain among themselves."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

import anyio.to_thread

from src.providers.decision.contract import DecisionError, DecisionGateway, DecisionRequest

FALLBACK_SECONDS = 5.0  # the longest wait for one gateway while another one remains
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


def default_gateways(names: Sequence[str]) -> dict[str, DecisionGateway]:
    from src.providers.decision.gateways import saved

    return {name: saved.SavedGateway(name) for name in names}


def _settled(answer: Mapping[str, Any] | None, minimum: float | None) -> bool:
    """Settled by the gateway's own verdict and, when the request names a minimum, that bar too."""
    if answer is None or answer.get("uncertain", True) or answer.get("unknown"):
        return False
    return minimum is None or answer.get("answer_confidence", 0) >= minimum - _EPSILON


def run(models: Sequence[str], request: DecisionRequest, *, gateways: Mapping[str, DecisionGateway] | None = None,
        on_usage: Callable[[dict[str, Any]], None] | None = None,
        check: Callable[[], float] | None = None, remote_timeout: float | None = None) -> DecisionResult:
    """Ask `models` from the top. `remote_timeout` caps each call to a gateway that is not local."""
    from src.providers.decision import gateway_client
    from src.runtime import confidentiality  # imports the providers, so not at the top

    names = tuple(models)
    gateways = gateways if gateways is not None else default_gateways(names)
    if confidentiality.current():
        names = tuple(name for name in names if gateway_client.is_trusted(name))
        if not names:
            raise DecisionError("this request holds confidential data and no trusted decision gateway can take it")
    problems: list[str] = []
    usable: list[tuple[str, DecisionGateway]] = []
    for name in names:
        gateway = gateways.get(name)
        if gateway is None or not gateway.available():
            problems.append(f"{name} is not available")
        else:
            usable.append((name, gateway))
    pending = dict(request.questions)
    answers: dict[str, dict[str, Any]] = {}
    tokens = 0
    for index, (name, gateway) in enumerate(usable):
        if not pending:
            break
        limit = check() if check else None
        if remote_timeout is not None and not gateway.local:
            limit = remote_timeout if limit is None else min(limit, remote_timeout)
        if index < len(usable) - 1:
            limit = FALLBACK_SECONDS if limit is None else min(limit, FALLBACK_SECONDS)
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
            previous = answers.get(qid)
            # A later gateway only replaces an earlier answer when it settles the question or is at least as sure.
            if (previous is None or _settled(answer, request.min_confidence)
                    or answer.get("answer_confidence", 0) >= previous.get("answer_confidence", 0)):
                answers[qid] = {**answer, "answered_by": name}
        pending = {q: s for q, s in pending.items() if not _settled(answers.get(q), request.min_confidence)}
    if not answers:
        raise DecisionError("; ".join(problems) or "no decision gateway could be asked")
    for qid in pending:
        if qid in answers:
            answers[qid]["uncertain"] = True
    return DecisionResult(answers, tokens, tuple(q for q in pending if q in answers))


async def arun(models: Sequence[str], request: DecisionRequest, **kwargs: Any) -> DecisionResult:
    return await anyio.to_thread.run_sync(lambda: run(models, request, **kwargs))


def ask_choice(subject: str, criteria: Mapping[str, str], question: str, *, models: Sequence[str], min_confidence: int,
               gateways: Mapping[str, DecisionGateway] | None = None,
               on_usage: Callable[[dict[str, Any]], None] | None = None, timeout: float | None = None) -> Choice:
    """One choice question: the answer with its confidence in percent (0-100)."""
    if len(criteria) < 2:
        raise DecisionError("a choice needs at least two options")
    request = DecisionRequest(subject, {"answer": {"type": "choice", "instructions": question, "criteria": dict(criteria)}},
                              min_confidence=min_confidence / 100)
    result = run(models, request, gateways=gateways, on_usage=on_usage,
                 check=(lambda: timeout) if timeout else None)
    answer = result.answers["answer"]
    return Choice(answer["choice"], round(answer["answer_confidence"] * 100), result.tokens, answer["answered_by"],
                  answer["answered_by"], answer.get("probabilities"))
