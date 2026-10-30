"""Architect files are validated at startup without shipping any definitions."""

import json

import pytest

from src.agents import agent_registry, agent_spec
from src import supervisor


BASE = {"role": "architect", "port": 9130, "llm": {"provider": "anthropic"},
        "kind": "code", "workers": ["worker"], "tools": {"deny": ["*"]}, "plan_tool": False}


def write(tmp_path, body, name="architect"):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_architect_defaults_and_supervisor_startup(tmp_path):
    spec = agent_spec.load_file(write(tmp_path, BASE))
    assert (spec.kind, spec.workers, spec.prefetch) == ("code", ("worker",), ())
    assert (spec.limits.max_units, spec.limits.max_parallel, spec.limits.unit_timeout_seconds,
            spec.limits.max_retries) == (12, 3, 120, 1)
    assert supervisor.child_env(spec)["AI_AGENT_FILE"] == str(spec.source)
    sup = supervisor.Supervisor([spec], command_for=lambda _: [])
    assert [child.spec for child in sup._children] == [spec]


@pytest.mark.parametrize("change,field", [
    ({"llm": {"provider": "decision"}}, "llm.provider"),
    ({"entry": True}, "entry"), ({"tools": {}}, "tools.deny"),
    *[({field: True}, field) for field in ("memory_recall", "skill_recall", "skill_learning", "plan_tool")],
    ({"kind": None}, "kind"), ({"kind": "research"}, "kind"),
    ({"workers": []}, "workers"), ({"workers": "worker"}, "workers"),
    ({"workers": [3]}, "workers"), ({"workers": [""]}, "workers"),
    ({"prefetch": "worker"}, "prefetch"), ({"prefetch": [None]}, "prefetch"),
    ({"limits": []}, "limits"), ({"limits": {"extra": 1}}, "limits.extra"),
    ({"extra": 1}, "extra"), ({"mode": "legacy"}, "mode"),
    *[({"limits": {field: value}}, f"limits.{field}") for field, value in (
        ("max_units", 0), ("max_parallel", True), ("unit_timeout_seconds", 0),
        ("unit_timeout_seconds", float("nan")), ("max_retries", -1), ("max_retries", None))],
])
def test_bad_architect_names_file_and_field(tmp_path, change, field):
    with pytest.raises(agent_spec.AgentSpecError) as error:
        agent_spec.load_file(write(tmp_path, {**BASE, **change}))
    assert "architect.json:" in str(error.value) and field in str(error.value)


def test_required_fields(tmp_path):
    for field in ("kind", "workers"):
        body = {key: value for key, value in BASE.items() if key != field}
        with pytest.raises(agent_spec.AgentSpecError, match=rf"architect.json: {field}"):
            agent_spec.load_file(write(tmp_path, body))


@pytest.mark.parametrize("field,value", [("kind", "code"), ("workers", ["worker"]),
                                         ("prefetch", []), ("limits", {})])
def test_architect_fields_are_role_specific(tmp_path, field, value):
    with pytest.raises(agent_spec.AgentSpecError, match=rf"architect.json: {field}"):
        agent_spec.load_file(write(tmp_path, {"role": "specialist", "port": 9100,
                                            "llm": {"provider": "openai"}, field: value}))


def setup_directory(tmp_path):
    write(tmp_path, {"role": "orchestrator", "port": 9100, "entry": True,
                     "llm": {"provider": "anthropic"}}, "entry")
    write(tmp_path, {"role": "specialist", "port": 9101, "llm": {"provider": "openai"}}, "worker")
    write(tmp_path, BASE)


@pytest.mark.parametrize("field", ["workers", "prefetch"])
@pytest.mark.parametrize("target", ["missing", "entry", "architect"])
def test_references_must_exist_and_be_specialists(tmp_path, field, target):
    setup_directory(tmp_path)
    write(tmp_path, {**BASE, field: [target]})
    with pytest.raises(agent_spec.AgentSpecError, match=rf"architect.json: {field}"):
        agent_spec.load_dir(tmp_path)


def test_kind_uniqueness_and_enabled_entry_port_rules(tmp_path):
    setup_directory(tmp_path)
    assert len(agent_spec.load_dir(tmp_path)) == 3
    write(tmp_path, {**BASE, "port": 9131}, "second")
    with pytest.raises(agent_spec.AgentSpecError, match=r"second.json: kind"):
        agent_spec.load_dir(tmp_path)
    write(tmp_path, {**BASE, "port": 9131, "enabled": False}, "second")
    assert len(agent_spec.load_dir(tmp_path)) == 4
    write(tmp_path, {**BASE, "port": 9101})
    with pytest.raises(agent_spec.AgentSpecError, match="port"):
        agent_spec.load_dir(tmp_path)
    write(tmp_path, BASE)
    write(tmp_path, {"role": "orchestrator", "port": 9100, "llm": {"provider": "anthropic"}}, "entry")
    with pytest.raises(agent_spec.AgentSpecError, match="exactly one"):
        agent_spec.load_dir(tmp_path)


def test_mode_is_orchestrator_only_and_defaults_to_legacy(tmp_path):
    body = {"role": "orchestrator", "port": 9100, "llm": {"provider": "anthropic"}}
    assert agent_spec.load_file(write(tmp_path, body)).mode == "legacy"
    assert agent_spec.load_file(write(tmp_path, {**body, "mode": "plan"})).mode == "plan"
    for mode in (None, "other", [], True):
        with pytest.raises(agent_spec.AgentSpecError, match="architect.json: mode"):
            agent_spec.load_file(write(tmp_path, {**body, "mode": mode}))
    for role in ("specialist", "router", "architect"):
        with pytest.raises(agent_spec.AgentSpecError, match="architect.json: mode"):
            agent_spec.load_file(write(tmp_path, {**body, "role": role, "mode": "legacy"}))


def test_architect_optional_flags_and_explicit_limits(tmp_path):
    body = {key: value for key, value in BASE.items() if key != "plan_tool"}
    spec = agent_spec.load_file(write(tmp_path, {**body, "prefetch": ["worker"], "limits": {
        "max_units": 2, "max_parallel": 1, "unit_timeout_seconds": 0.5, "max_retries": 0}}))
    assert not spec.plan_tool
    assert spec.prefetch == ("worker",)
    assert spec.limits.unit_timeout_seconds == 0.5 and spec.limits.max_retries == 0


def test_architect_registry_metadata(tmp_path):
    spec = agent_spec.load_file(write(tmp_path, BASE))
    agent_registry.register(spec.id, spec.label, "http://localhost:9130/mcp", role=spec.role,
                            kind=spec.kind, workers=list(spec.workers))
    row = agent_registry.get_agent(spec.id)
    assert row["kind"] == "code" and row["workers"] == ["worker"]
    agent_registry.write_definitions([spec])
    assert agent_registry.read_definitions()[0]["kind"] == "code"
