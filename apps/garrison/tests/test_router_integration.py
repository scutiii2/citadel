import asyncio
from unittest.mock import AsyncMock

import pytest

from src.agents import agent_spec, agent_routing, delegation, router_client, router_routing
from src.agents.agent_spec import AgentSpec, LlmSpec, RosterEntry, TierInfo
from src.agents.router_contract import DecisionOutcome, RouteResponse
from src.core import approvals, internal_auth


def setup(monkeypatch, response):
    monkeypatch.setattr(agent_spec, "_current", AgentSpec(id="ember", label="Ember", port=9100,
        llm=LlmSpec(provider="anthropic"), entry=True, orchestrator=True))
    monkeypatch.setattr(internal_auth, "TOKEN", "test")
    roster = [RosterEntry("ops", "Ops", "server", (TierInfo("standard", "model", "normal"),), tool_allow=("tool_srv_*",))]
    monkeypatch.setattr(agent_routing, "roster_for", AsyncMock(return_value=roster))
    monkeypatch.setattr(router_routing.model_tiers, "own_tiers", lambda: [TierInfo("standard", "model", "normal")])
    decide = AsyncMock(return_value=response)
    monkeypatch.setattr(router_client, "decide", decide)
    return decide


def test_uncertain_agent_with_settled_size_uses_ember_tier(monkeypatch):
    setup(monkeypatch, RouteResponse(policy_revision="x", agent=DecisionOutcome(reason="uncertain"),
        size=DecisionOutcome(choice="large", uncertain=False), model_tier="standard"))
    result, tier, note = asyncio.run(router_routing.route_turn("help me investigate", [], None, "r", 0))
    assert result is None and tier == "standard" and "router" in note


def test_settled_route_dispatches_once_and_preserves_explicit_tier(monkeypatch):
    setup(monkeypatch, RouteResponse(policy_revision="x", agent=DecisionOutcome(choice="ops", uncertain=False),
        size=DecisionOutcome(choice="tiny", uncertain=False), model_tier="light"))
    calls = []
    monkeypatch.setattr(delegation, "dispatch", lambda args, depth: calls.append(args) or "done")
    result, tier, _ = asyncio.run(router_routing.route_turn("check server", [], None, "r", 0, "heavy"))
    assert result.response == "done" and calls[0]["model_tier"] == "heavy" and len(calls) == 1


def test_approval_skips_agent_choice_but_allows_tier(monkeypatch):
    decide = setup(monkeypatch, RouteResponse(policy_revision="x"))
    token = approvals.bind(approvals.ApprovalPolicy("ask"))
    try:
        asyncio.run(router_routing.route_turn("investigate server", [], None, "r", 0))
    finally:
        approvals.reset(token)
    assert decide.call_args.args[0].choose_agent is False
    assert decide.call_args.args[0].choose_tier is True


def test_delegated_calls_never_route(monkeypatch):
    decide = setup(monkeypatch, None)
    assert asyncio.run(router_routing.route_turn("hello", [], None, "r", 1)) == (None, None, "")
    decide.assert_not_called()


def test_absent_router_does_not_reactivate_jev(monkeypatch):
    setup(monkeypatch, None)
    monkeypatch.setattr(router_routing, "legacy_classifier", lambda: pytest.fail("legacy path used"), raising=False)
    assert asyncio.run(router_routing.route_turn("hello", [], None, "r", 0)) == (None, None, "")


def test_unknown_explicit_tier_keeps_existing_model_resolution(monkeypatch):
    decide = setup(monkeypatch, None)
    assert asyncio.run(router_routing.route_turn("hello", [], None, "r", 0, "unknown-tier")) == (None, None, "")
    decide.assert_not_called()


def test_empty_question_falls_back_without_request_validation_error(monkeypatch):
    decide = setup(monkeypatch, None)
    assert asyncio.run(router_routing.route_turn("", [], None, "r", 0)) == (None, None, "")
    decide.assert_not_called()
