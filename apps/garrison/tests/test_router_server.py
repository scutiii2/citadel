import asyncio
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.agents import agent_spec
from src.agents.roles.router.router_contract import RouterPolicy, RouteResponse
from src.agents.roles.router.router_contract import VoterUsage
from src.agents.roles.router import router_service
from src.runtime import internal_auth


def test_route_fails_closed_without_configured_token(monkeypatch):
    monkeypatch.setattr(internal_auth, "TOKEN", "")
    with pytest.raises(ValueError, match="token"):
        asyncio.run(router_service.route({}, {}))


def test_route_requires_valid_token_and_router_role(monkeypatch):
    monkeypatch.setattr(internal_auth, "TOKEN", "internal")
    with pytest.raises(ValueError, match="token"):
        asyncio.run(router_service.route({}, {"X-Internal-Token": "wrong"}))
    with pytest.raises(ValueError, match="Router"):
        asyncio.run(router_service.route({}, {"X-Internal-Token": "internal"}))


def test_authenticated_route_validates_and_runs_engine(monkeypatch):
    monkeypatch.setattr(internal_auth, "TOKEN", "internal")
    monkeypatch.setattr(agent_spec, "current", lambda: SimpleNamespace(
        internal_role="router", decision=RouterPolicy()))
    class Engine:
        def route(self, request, policy, **kwargs):
            return RouteResponse(policy_revision=policy.revision())
    monkeypatch.setattr(router_service, "_engine", Engine())
    result = asyncio.run(router_service.route({"subject": "hello", "request_id": "r"},
                                             {"X-Internal-Token": "internal"}))
    assert result["agent"]["uncertain"]


def test_deadline_returns_partial_usage_and_freezes_late_worker_records(monkeypatch):
    monkeypatch.setattr(internal_auth, "TOKEN", "internal")
    monkeypatch.setattr(agent_spec, "current", lambda: SimpleNamespace(
        internal_role="router", decision=RouterPolicy(deadline_seconds=1)))
    release, late = threading.Event(), threading.Event()
    logs = []
    monkeypatch.setattr(router_service.usage_log, "_write", lambda row, directory: logs.append(row))
    record = VoterUsage(provider_id="laya", model="typed-decisions", started_at="2026-10-21T00:00:00+00:00",
                        duration_ms=1, input_tokens=7, output_tokens=0, ok=True)
    class SlowEngine:
        def route(self, request, policy, **kwargs):
            kwargs["on_usage"](record)
            release.wait(3)
            kwargs["on_usage"](record)
            late.set()
            return RouteResponse(policy_revision=policy.revision())
    monkeypatch.setattr(router_service, "_engine", SlowEngine())
    started = time.monotonic()
    try:
        result = asyncio.run(router_service.route({"subject": "hello", "request_id": "slow-route"},
                                                 {"X-Internal-Token": "internal"}))
        assert time.monotonic()-started < 2
        assert result["agent"]["reason"] == "timeout" and len(result["usage"]) == 1
        release.set()
        assert late.wait(1)
        assert len(result["usage"]) == 1 and len(logs) == 2
    finally:
        release.set()
