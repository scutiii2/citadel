import json
import math

import pytest

from src.agents import agent_spec, agent_store
from src.agents.roles.router.router_contract import RouterPolicy, RouteRequest, RouteResponse


def definition(**changes):
    return {"port": 9117, "role": 'router', "delegable": False,
            "plan_tool": False, "tools": {"deny": ["*"]},
            "llm": {"provider": "decision"}, **changes}


def write(tmp_path, name="router", **changes):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(definition(**changes)), encoding="utf-8")
    return path


def test_policy_defaults():
    p = RouterPolicy()
    assert p.deadline_seconds == 10 and p.remote_timeout_seconds == 3
    assert p.size_tiers["hardest"] == "heavy"
    assert p.thresholds["2"]["laya-typed"] == .8
    assert RouterPolicy.model_validate(p.model_dump()) == p


@pytest.mark.parametrize("value", [
    {"deadline_seconds": 0}, {"deadline_seconds": 31}, {"deadline_seconds": math.nan},
    {"thresholds": {"2": {"jev": math.nan}}}, {"unknown": True},
    {"size_tiers": {"tiny": "imaginary"}},
    {"english": False, "typed": False, "fallback": False},
])
def test_policy_rejects_invalid_settings(value):
    with pytest.raises(ValueError):
        RouterPolicy.model_validate(value)


def test_router_role_loads_and_persists_policy(tmp_path):
    spec = agent_spec.load_file(write(tmp_path, decision={"deadline_seconds": 8}))
    assert spec.internal_role == "router"
    assert spec.decision.deadline_seconds == 8
    assert not spec.delegable


@pytest.mark.parametrize("changes", [
    {"entry": True}, {"role": 'orchestrator'}, {"delegable": True},
    {"plan_tool": True}, {"memory_recall": True}, {"tools": {"deny": []}},
    {"llm": {"provider": "anthropic"}}, {"role": 'invented'},
])
def test_router_role_cannot_gain_chat_privileges(tmp_path, changes):
    with pytest.raises(agent_spec.AgentSpecError):
        agent_spec.load_file(write(tmp_path, **changes))


def test_two_enabled_routers_rejected_by_directory_and_admin(tmp_path):
    write(tmp_path)
    entry = tmp_path / "ember.json"
    entry.write_text(json.dumps({"role": "specialist", "port": 9100, "entry": True, "llm": {"provider": "anthropic"}}))
    with pytest.raises(agent_store.AgentStoreError, match="router"):
        agent_store.create_agent("second", definition(port=9118), tmp_path)
    write(tmp_path, "second", port=9118)
    with pytest.raises(agent_spec.AgentSpecError, match="router"):
        agent_spec.load_dir(tmp_path)


def test_non_router_cannot_carry_policy(tmp_path):
    with pytest.raises(agent_spec.AgentSpecError, match="decision"):
        agent_spec.load_file(write(tmp_path, role="specialist", decision={}))


def test_response_is_strict_and_uncertain_is_explicit():
    response = RouteResponse.model_validate({"policy_revision": "1"})
    assert response.agent.uncertain and response.size.uncertain
    with pytest.raises(ValueError):
        RouteResponse.model_validate({"policy_revision": "1", "agent": {"confidence": float("nan")}})
    with pytest.raises(ValueError):
        RouteRequest.model_validate({"subject": "x", "request_id": "x", "url": "http://attacker"})
