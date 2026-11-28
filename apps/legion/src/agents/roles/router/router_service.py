"""Authenticated Router operation, bounded independently of inference threads."""
from __future__ import annotations

import threading
from functools import partial

import anyio

from src.agents import agent_spec
from src.agents.roles.router.router_contract import DecisionOutcome, RouteRequest, RouteResponse
from src.agents.roles.router.router_engine import RouterEngine
from src.runtime import usage_log
from src.citadel_auth import current_caller
from src.providers import cancellation
from src.providers.decision import gateway_client as decision_gateway

_engine = RouterEngine()


def status_summary() -> dict:
    spec = agent_spec.current()
    names = spec.llm.gateway_names
    summary = spec.decision.summary()
    local = next((name for name in names if decision_gateway.is_local(name)), None)
    if local:
        summary["local_status"] = "loaded" if decision_gateway.is_reachable(local) else "unavailable"
    # False only when there is a second model and none after the first can be asked.
    summary["fallback_available"] = len(names) < 2 or any(decision_gateway.is_usable(name) for name in names[1:])
    return summary


async def route(raw: dict, headers) -> dict:
    if current_caller() is None:
        raise ValueError("Router requires an authenticated service caller")
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
        with lock:
            if accepting:
                records.append(row)
        # Actual late completions remain visible in the Router's local usage log.
        try:
            from src.agents.roles.router.router_client import usage_row
            usage_log._write(usage_row(row, request.request_id,
                delegated_by=request.entry.id if request.entry else ""), usage_log.usage_dir())
        except OSError:
            pass

    cancellation.register(request.request_id)
    result = None
    try:
        with anyio.move_on_after(policy.deadline_seconds):
            result = await anyio.to_thread.run_sync(partial(_engine.route, request, policy, models=spec.llm.gateway_names,
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
