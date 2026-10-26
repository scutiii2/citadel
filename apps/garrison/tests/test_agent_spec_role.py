"""Agent files declare one role; bad role/provider/tool combinations are refused."""

import json
from pathlib import Path

import pytest

from src.agents import agent_spec
from src.agents.agent_spec import AgentSpecError


def load(tmp_path: Path, body: dict, name: str = "a") -> agent_spec.AgentSpec:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return agent_spec.load_file(path)


BASE = {"port": 9100, "llm": {"provider": "anthropic"}}


def test_role_is_required(tmp_path):
    with pytest.raises(AgentSpecError, match="role"):
        load(tmp_path, BASE)


def test_unknown_role_is_refused(tmp_path):
    with pytest.raises(AgentSpecError, match="role"):
        load(tmp_path, {**BASE, "role": "boss"})


def test_old_flags_are_unknown_keys(tmp_path):
    for key, value in (("orchestrator", True), ("internal_role", "router")):
        with pytest.raises(AgentSpecError, match=key):
            load(tmp_path, {**BASE, "role": "specialist", key: value})


def test_orchestrator_role_sets_the_property(tmp_path):
    spec = load(tmp_path, {**BASE, "role": "orchestrator", "entry": True})
    assert spec.role == "orchestrator" and spec.orchestrator is True and spec.internal_role is None


def test_specialist_defaults(tmp_path):
    spec = load(tmp_path, {**BASE, "role": "specialist"})
    assert spec.orchestrator is False and spec.delegable is True


def test_router_needs_laya_provider_no_tools_no_entry(tmp_path):
    router = {"port": 9117, "role": "router", "entry": False, "delegable": False, "plan_tool": False,
              "llm": {"provider": "laya", "gateway": "local"}, "tools": {"allow": [], "deny": ["*"]}}
    spec = load(tmp_path, router)
    assert spec.role == "router" and spec.internal_role == "router"
    with pytest.raises(AgentSpecError, match="router"):
        load(tmp_path, {**router, "llm": {"provider": "anthropic"}})
    with pytest.raises(AgentSpecError, match="router"):
        load(tmp_path, {**router, "tools": {"allow": ["x"], "deny": []}})


def test_decision_block_only_for_router(tmp_path):
    with pytest.raises(AgentSpecError, match="decision"):
        load(tmp_path, {**BASE, "role": "specialist", "decision": {}})


def test_laya_provider_cannot_be_an_orchestrator(tmp_path):
    with pytest.raises(AgentSpecError, match="Laya"):
        load(tmp_path, {"port": 9111, "role": "orchestrator", "llm": {"provider": "laya", "gateway": "local"}})
