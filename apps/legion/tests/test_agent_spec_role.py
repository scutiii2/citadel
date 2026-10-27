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


def test_legacy_flags_upgrade_to_a_role(tmp_path):
    assert load(tmp_path, {**BASE, "orchestrator": True, "entry": True}).role == "orchestrator"
    assert load(tmp_path, {**BASE, "role": "specialist", "orchestrator": False}).role == "specialist"


def test_stored_override_without_role_is_a_specialist(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({**BASE, "role": "specialist"}), encoding="utf-8")
    overrides = agent_spec.overrides_path_for(tmp_path)
    overrides.parent.mkdir(parents=True)
    overrides.write_text(json.dumps({"a": {**BASE, "orchestrator": True, "entry": True}, "b": dict(BASE)}), encoding="utf-8")
    assert agent_spec.load_file(tmp_path / "a.json").role == "orchestrator"
    assert agent_spec.read_overrides(tmp_path)["b"]["role"] == "specialist"


def test_legacy_flags_in_stored_overrides_load(tmp_path):
    overrides = tmp_path / ".overrides" / "agent_overrides.json"
    overrides.parent.mkdir()
    entry = {**BASE, "entry": True}
    overrides.write_text(json.dumps({
        "on": {**entry, "orchestrator": True},
        "off": {**entry, "orchestrator": False},
        "plain": dict(entry),
        "kept": {**entry, "role": "specialist", "orchestrator": True},
        "rtr": {"port": 9101, "llm": {"provider": "decision"}, "internal_role": "router",
                "delegable": False, "plan_tool": False, "tools": {"deny": ["*"]}},
    }), encoding="utf-8")
    roles = {name: agent_spec.load_file(tmp_path / f"{name}.json").role for name in ("on", "off", "plain", "kept", "rtr")}
    assert roles == {"on": "orchestrator", "off": "specialist", "plain": "specialist", "kept": "specialist", "rtr": "router"}


def test_legacy_flags_in_a_tracked_file_still_need_a_role(tmp_path):
    assert load(tmp_path, {**BASE, "orchestrator": True, "entry": True}).role == "orchestrator"
    with pytest.raises(AgentSpecError, match="role"):
        load(tmp_path, {**BASE, "orchestrator": False})


def test_orchestrator_role_sets_the_property(tmp_path):
    spec = load(tmp_path, {**BASE, "role": "orchestrator", "entry": True})
    assert spec.role == "orchestrator" and spec.orchestrator is True and spec.internal_role is None


def test_specialist_defaults(tmp_path):
    spec = load(tmp_path, {**BASE, "role": "specialist"})
    assert spec.orchestrator is False and spec.delegable is True


def test_router_needs_decision_provider_no_tools_no_entry(tmp_path):
    router = {"port": 9117, "role": "router", "entry": False, "delegable": False, "plan_tool": False,
              "llm": {"provider": "decision"}, "tools": {"allow": [], "deny": ["*"]}}
    spec = load(tmp_path, router)
    assert spec.role == "router" and spec.internal_role == "router"
    with pytest.raises(AgentSpecError, match="router"):
        load(tmp_path, {**router, "llm": {"provider": "anthropic"}})
    with pytest.raises(AgentSpecError, match="router"):
        load(tmp_path, {**router, "tools": {"allow": ["x"], "deny": []}})


def test_decision_block_only_for_router(tmp_path):
    with pytest.raises(AgentSpecError, match="decision"):
        load(tmp_path, {**BASE, "role": "specialist", "decision": {}})


def test_decision_provider_cannot_be_an_orchestrator(tmp_path):
    with pytest.raises(AgentSpecError, match="decision"):
        load(tmp_path, {"port": 9111, "role": "orchestrator", "llm": {"provider": "decision"}})


def test_router_inherits_llm_strategy_unless_decision_overrides(tmp_path):
    router = {"port": 9117, "role": "router", "entry": False, "delegable": False, "plan_tool": False,
              "tools": {"allow": [], "deny": ["*"]}}
    inherited = load(tmp_path, {**router, "llm": {"provider": "decision", "strategy": "laya-only", "min_confidence": 0.8}})
    assert (inherited.decision.strategy, inherited.decision.min_confidence) == ("laya-only", 0.8)
    overridden = load(tmp_path, {**router, "llm": {"provider": "decision", "strategy": "laya-only"}, "decision": {"strategy": "jev-only"}})
    assert overridden.decision.strategy == "jev-only"
