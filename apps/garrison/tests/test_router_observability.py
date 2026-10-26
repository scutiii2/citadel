import asyncio
from dataclasses import replace

import pytest

from src.agents import agent_spec
from src.agents.roles.router import router_service
from src.agents.roles.router.router_contract import RouterPolicy
from src.runtime import internal_auth


class _Service:
    def __init__(self, healthy):
        self.configured, self._healthy = True, healthy

    def health(self):
        return self._healthy


def test_readiness_distinguishes_a_running_laya_service_and_unavailable_fallback(monkeypatch):
    spec = replace(agent_spec.current(), role="router", decision=RouterPolicy())
    monkeypatch.setattr(agent_spec, "current", lambda: spec)
    monkeypatch.setattr(router_service.laya_model, "agent", lambda: _Service(True))
    monkeypatch.setattr(router_service.laya_model, "configured", lambda: True)
    monkeypatch.setattr(router_service.JevGateway, "available", lambda self: False)
    summary = router_service.status_summary()
    assert summary["local_status"] == "loaded"
    assert summary["fallback_available"] is False
    assert "thresholds" not in summary


@pytest.mark.parametrize(("strategy", "fallback_available"), [
    ("laya-only", False), ("jev-only", True), ("both", True),
])
def test_fallback_readiness_respects_selected_strategy(monkeypatch, strategy, fallback_available):
    spec = replace(agent_spec.current(), role="router", decision=RouterPolicy(strategy=strategy))
    monkeypatch.setattr(agent_spec, "current", lambda: spec)
    monkeypatch.setattr(router_service.laya_model, "configured", lambda: False)
    monkeypatch.setattr(router_service.JevGateway, "available", lambda self: True)
    summary = router_service.status_summary()
    assert summary["strategy"] == strategy
    assert summary["fallback_available"] is fallback_available


def test_an_unreachable_or_missing_laya_service_publishes_degraded_state(monkeypatch):
    spec = replace(agent_spec.current(), role="router", decision=RouterPolicy())
    monkeypatch.setattr(agent_spec, "current", lambda: spec)
    monkeypatch.setattr(router_service.laya_model, "configured", lambda: True)
    monkeypatch.setattr(router_service.laya_model, "agent", lambda: _Service(False))
    assert router_service.status_summary()["local_status"] == "unavailable"
    monkeypatch.setattr(router_service.laya_model, "configured", lambda: False)
    assert router_service.status_summary()["local_status"] == "unavailable"


def test_failed_attempts_remain_in_trace_without_becoming_billable_usage():
    from src.agents.roles.router.router_client import usage_row
    from src.agents.roles.router.router_contract import VoterUsage
    row = usage_row(VoterUsage(provider_id="jev", model="jev-latest", started_at="2026-10-21T00:00:00+00:00",
        duration_ms=10, ok=False, reason="backend_failed"), "r")
    assert row["agent_id"] == "router" and row["total_tokens"] is None
    assert row["routing"]["reason"] == "backend_failed"
