"""Authenticated Router operation, bounded independently of inference threads."""
from __future__ import annotations

import hmac
import threading
from functools import partial

import anyio

from src.agents import agent_spec
from src.agents.router_contract import DecisionOutcome, RouteRequest, RouteResponse
from src.agents.router_engine import RouterEngine
from src.core import internal_auth, usage_log
from src.llm import cancellation
from src.llm import decision

_engine = RouterEngine()


def status_summary() -> dict:
    from src.agents.router_models import cached_checkpoint

    policy = agent_spec.current().decision
    models = [model for name, model in _engine.voters.items()
              if (name == "laya-english" and policy.english) or (name == "laya-typed" and policy.typed)]
    local_status = "loaded" if models and all(m._engine is not None for m in models) else "not_loaded"
    try:
        for model in models:
            if model._engine is None:
                cached_checkpoint(model._checkpoint)
    except RuntimeError:
        local_status = "unavailable"
    return {**policy.summary(), "local_status": local_status,
            "fallback_available": bool(policy.fallback and decision.available("triage", ("laya",)))}


async def route(raw: dict, headers) -> dict:
    provided = (headers or {}).get("X-Internal-Token", "")
    if not internal_auth.TOKEN or not hmac.compare_digest(provided, internal_auth.TOKEN):
        raise ValueError("Router requires a valid configured internal token")
    spec = agent_spec.current()
    if spec.internal_role != "router":
        raise ValueError("This is not a Router agent")
    try:
        request = RouteRequest.model_validate(raw)
    except ValueError:
        raise ValueError("Invalid internal routing request") from None
    policy = spec.decision
    cancelled = threading.Event()
    lock = threading.Lock()
    records = []
    accepting = True

    def observed(row):
        nonlocal accepting
        with lock:
            if accepting:
                records.append(row)
        # Actual late completions remain visible in the Router's local usage log.
        try:
            from src.agents.router_client import usage_row
            usage_log._write(usage_row(row, request.request_id,
                delegated_by=request.entry.id if request.entry else ""), usage_log.usage_dir())
        except OSError:
            pass

    cancellation.register(request.request_id)
    result = None
    try:
        with anyio.move_on_after(policy.deadline_seconds):
            result = await anyio.to_thread.run_sync(partial(_engine.route, request, policy,
                cancelled=lambda: cancelled.is_set() or cancellation.is_cancelled(request.request_id),
                on_usage=observed), abandon_on_cancel=True)
    finally:
        cancelled.set()
        with lock:
            accepting = False
            snapshot = list(records)
        cancellation.clear(request.request_id)
    if result is None:
        result = RouteResponse(policy_revision=policy.revision(), usage=snapshot,
            agent=DecisionOutcome(reason="timeout"), size=DecisionOutcome(reason="timeout"))
    return result.model_dump()
