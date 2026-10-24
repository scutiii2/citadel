"""agent_spec.py tests: defaults, every validation error, the set-level
checks (ports, exactly one entry), the AI_AGENT_FILE requirement, and the
env-var hand-off a child does before importing agent_config."""

from __future__ import annotations

import json
import os
import ast
from pathlib import Path

import pytest

from src.agents import agent_spec
from src.agents.agent_spec import AgentSpecError, ToolScope


def _write(directory, name, data):
    path = directory / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_file_applies_defaults(tmp_path):
    spec = agent_spec.load_file(_write(tmp_path, "calc", {"port": 9103, "llm": {"provider": "anthropic"}}))

    assert spec.id == "calc"
    assert spec.label == "calc"
    assert spec.port == 9103
    assert spec.enabled is True
    assert spec.entry is False
    assert spec.persona == ""
    assert spec.focus == ""
    assert spec.orchestrator is False
    assert spec.tools == ToolScope()
    assert spec.llm.provider == "anthropic"
    assert spec.llm.reasoning_effort == "off"
    assert spec.source == tmp_path / "calc.json"
    assert spec.llm.fallback_gateways == ()


def test_fallback_gateways_preserve_order_and_primary_environ(tmp_path, monkeypatch):
    spec = agent_spec.load_file(_write(tmp_path, "calc", {"port": 9103, "llm": {
        "provider": "anthropic", "fallback_gateways": [
            {"gateway": "openrouter", "model": "mapped"}, "bedrock"],
    }}))
    assert spec.llm.fallback_gateways == (
        agent_spec.GatewayChoice("openrouter", "mapped"), agent_spec.GatewayChoice("bedrock"))
    for key in ("AI_AGENT_PROVIDER", "AI_AGENT_GATEWAY", "AI_AGENT_MODEL", "AI_AGENT_PORT"):
        monkeypatch.setenv(key, "previous")
    agent_spec.apply_to_environ(spec)
    assert os.environ["AI_AGENT_GATEWAY"] == "claude"
    assert os.environ["AI_AGENT_MODEL"] == ""


@pytest.mark.parametrize("provider,value", [
    ("anthropic", "openrouter"), ("anthropic", None), ("anthropic", [{}]),
    ("anthropic", [{"gateway": ""}]), ("anthropic", [{"gateway": 3}]),
    ("anthropic", [{"gateway": "backup", "typo": True}]),
    ("anthropic", ["backup", "backup"]), ("anthropic", ["claude"]),
    ("anthropic", [True]), ("anthropic", [{"gateway": "backup", "model": 3}]),
    ("laya", ["backup"]),
])
def test_invalid_fallback_gateways_name_file_and_field(tmp_path, provider, value):
    path = _write(tmp_path, "calc", {"port": 9103, "llm": {
        "provider": provider, "fallback_gateways": value}})
    with pytest.raises(AgentSpecError, match=r"calc.json: llm.fallback_gateways"):
        agent_spec.load_file(path)


def test_laya_specialist_is_local_and_needs_no_generation_settings(tmp_path, monkeypatch):
    for key in ("AI_AGENT_PROVIDER", "AI_AGENT_GATEWAY", "AI_AGENT_MODEL", "AI_AGENT_PORT"):
        monkeypatch.setenv(key, os.getenv(key, ""))
    spec = agent_spec.load_file(_write(tmp_path, "triage-assistant", {
        "port": 9110, "llm": {"provider": "laya"}, "tools": {"deny": ["*"]},
    }))
    agent_spec.apply_to_environ(spec)
    assert os.environ["AI_AGENT_PROVIDER"] == "laya"
    assert os.environ["AI_AGENT_GATEWAY"] == "local"
    assert not spec.tools.allows("any_tool")


@pytest.mark.parametrize("extra", [
    {"entry": True}, {"orchestrator": True},
    {"llm": {"provider": "laya", "gateway": "openrouter"}},
    {"llm": {"provider": "laya", "model": "gpt-x"}},
    {"llm": {"provider": "laya", "max_tokens": 100}},
    {"llm": {"provider": "laya", "reasoning_effort": "high"}},
])
def test_laya_rejects_cloud_or_generation_configuration(tmp_path, extra):
    data = {"port": 9110, "llm": {"provider": "laya"}, **extra}
    with pytest.raises(AgentSpecError, match="Laya triage"):
        agent_spec.load_file(_write(tmp_path, "triage-assistant", data))


def test_load_file_reads_every_field(tmp_path):
    data = {
        "label": "Ember",
        "port": 9100,
        "enabled": True,
        "entry": True,
        "llm": {
            "provider": "openai", "gateway": "azure", "model": "gpt-x", "temperature": 0.2,
            "reasoning_effort": "high", "max_tokens": 4096, "max_tool_rounds": 8,
        },
        "persona": "You coordinate.",
        "focus": "Everything.",
        "tools": {"allow": ["calc_*"], "deny": ["calc_secret"]},
        "orchestrator": True,
    }
    spec = agent_spec.load_file(_write(tmp_path, "orchestrator", data))

    assert spec.label == "Ember"
    assert spec.llm.gateway == "azure"
    assert spec.llm.temperature == 0.2
    assert spec.llm.max_tool_rounds == 8
    assert spec.tools == ToolScope(allow=("calc_*",), deny=("calc_secret",))


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"llm": {"provider": "anthropic"}}, "port"),
        ({"port": 9100}, "llm"),
        ({"port": 9100, "llm": {}}, "llm.provider"),
        ({"port": 9100, "llm": {"provider": "gemini"}}, "llm.provider"),
        ({"port": 9100, "llm": {"provider": "anthropic"}, "colour": "red"}, "colour"),
        ({"port": 9100, "llm": {"provider": "anthropic", "temp": 1}}, "llm.temp"),
        ({"port": "9100", "llm": {"provider": "anthropic"}}, "port"),
        ({"port": 0, "llm": {"provider": "anthropic"}}, "port"),
        ({"port": 9100, "llm": {"provider": "anthropic", "temperature": 3}}, "llm.temperature"),
        ({"port": 9100, "llm": {"provider": "anthropic", "reasoning_effort": "max"}}, "llm.reasoning_effort"),
        ({"port": 9100, "llm": {"provider": "anthropic", "max_tokens": 0}}, "llm.max_tokens"),
        ({"port": 9100, "llm": {"provider": "anthropic"}, "tools": {"allow": "calc_*"}}, "tools.allow"),
        ({"port": 9100, "llm": {"provider": "anthropic"}, "orchestrator": True, "routing": {"laya": True}}, "routing"),
        ({"port": 9100, "llm": {"provider": "anthropic"}, "entry": "yes"}, "entry"),
        ({"port": None, "llm": {"provider": "anthropic"}}, "port"),
        ({"port": 9100, "llm": {"provider": "anthropic"}, "enabled": None}, "enabled"),
        ({"port": 9100, "llm": {"provider": "anthropic"}, "entry": None}, "entry"),
        ({"port": 9100, "llm": {"provider": "anthropic"}, "orchestrator": None}, "orchestrator"),
        ({"port": 9100, "llm": {"provider": "anthropic", "reasoning_effort": None}}, "llm.reasoning_effort"),
    ],
)
def test_load_file_rejects_bad_fields(tmp_path, data, message):
    with pytest.raises(AgentSpecError) as error:
        agent_spec.load_file(_write(tmp_path, "calc", data))
    assert "calc.json" in str(error.value)
    assert message in str(error.value)


def test_load_file_rejects_bad_json(tmp_path):
    path = tmp_path / "calc.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(AgentSpecError, match="calc.json"):
        agent_spec.load_file(path)


def test_load_file_rejects_a_bad_id(tmp_path):
    with pytest.raises(AgentSpecError, match="id"):
        agent_spec.load_file(_write(tmp_path, "Calc_Agent", {"port": 9100, "llm": {"provider": "anthropic"}}))


def test_load_dir_requires_exactly_one_entry(tmp_path):
    _write(tmp_path, "a", {"port": 9100, "llm": {"provider": "anthropic"}})
    _write(tmp_path, "b", {"port": 9101, "llm": {"provider": "anthropic"}})
    with pytest.raises(AgentSpecError, match="entry"):
        agent_spec.load_dir(tmp_path)

    _write(tmp_path, "a", {"port": 9100, "entry": True, "llm": {"provider": "anthropic"}})
    _write(tmp_path, "b", {"port": 9101, "entry": True, "llm": {"provider": "anthropic"}})
    with pytest.raises(AgentSpecError, match="a.json, b.json"):
        agent_spec.load_dir(tmp_path)


def test_load_dir_ignores_disabled_files_for_set_checks(tmp_path):
    _write(tmp_path, "a", {"port": 9100, "entry": True, "llm": {"provider": "anthropic"}})
    _write(tmp_path, "b", {"port": 9100, "entry": True, "enabled": False, "llm": {"provider": "anthropic"}})

    specs = agent_spec.load_dir(tmp_path)

    assert [s.id for s in specs] == ["a", "b"]


def test_load_dir_rejects_duplicate_ports(tmp_path):
    _write(tmp_path, "a", {"port": 9100, "entry": True, "llm": {"provider": "anthropic"}})
    _write(tmp_path, "b", {"port": 9100, "llm": {"provider": "anthropic"}})
    with pytest.raises(AgentSpecError, match="9100"):
        agent_spec.load_dir(tmp_path)


def test_load_dir_rejects_an_empty_directory(tmp_path):
    with pytest.raises(AgentSpecError, match="no agent files"):
        agent_spec.load_dir(tmp_path)


def test_tool_scope_allow_deny_and_unmatched():
    everything = ToolScope()
    assert everything.allows("anything") is True

    scope = ToolScope(allow=("calc_*", "convert_*"), deny=("calc_secret",))
    assert scope.allows("calc_add") is True
    assert scope.allows("calc_secret") is False
    assert scope.allows("weather_now") is False
    assert scope.unmatched(["calc_add", "calc_secret"]) == ["convert_*"]


def test_current_requires_ai_agent_file(monkeypatch):
    monkeypatch.delenv("AI_AGENT_FILE", raising=False)
    monkeypatch.setattr(agent_spec, "_current", None)
    with pytest.raises(AgentSpecError, match="AI_AGENT_FILE is not set"):
        agent_spec.current()


def test_effective_gateway_for_a_file_spec_ignores_the_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_AGENT_GATEWAY", "openrouter")
    spec = agent_spec.load_file(_write(tmp_path, "calc", {"port": 9103, "llm": {"provider": "anthropic"}}))
    assert spec.effective_gateway() is None


def test_current_reads_ai_agent_file_and_caches(tmp_path, monkeypatch):
    path = _write(tmp_path, "calc", {"port": 9103, "llm": {"provider": "anthropic"}})
    monkeypatch.setenv("AI_AGENT_FILE", str(path))
    monkeypatch.setattr(agent_spec, "_current", None)

    first = agent_spec.current()
    path.write_text("{broken", encoding="utf-8")

    assert first.id == "calc"
    assert agent_spec.current() is first


def test_apply_to_environ_sets_provider_gateway_model_and_port(tmp_path, monkeypatch):
    for name in ("AI_AGENT_PROVIDER", "AI_AGENT_GATEWAY", "AI_AGENT_MODEL", "AI_AGENT_PORT"):
        monkeypatch.delenv(name, raising=False)
    spec = agent_spec.load_file(_write(tmp_path, "calc", {"port": 9103, "llm": {"provider": "openai"}}))

    agent_spec.apply_to_environ(spec)

    assert os.environ["AI_AGENT_PROVIDER"] == "openai"
    # No gateway in the file: pin the provider default so .env's
    # AI_AGENT_GATEWAY (loaded later with setdefault) cannot override it.
    assert os.environ["AI_AGENT_GATEWAY"] == "gpt"
    assert os.environ["AI_AGENT_MODEL"] == ""
    assert os.environ["AI_AGENT_PORT"] == "9103"


def test_llm_min_and_max_tier_are_read(tmp_path):
    spec = agent_spec.load_file(_write(tmp_path, "calc", {
        "port": 9103, "llm": {"provider": "anthropic", "min_tier": "light", "max_tier": "standard"},
    }))
    assert (spec.llm.min_tier, spec.llm.max_tier) == ("light", "standard")


def test_llm_tiers_default_to_unbounded(tmp_path):
    spec = agent_spec.load_file(_write(tmp_path, "calc", {"port": 9103, "llm": {"provider": "anthropic"}}))
    assert (spec.llm.min_tier, spec.llm.max_tier) == (None, None)


@pytest.mark.parametrize("key", ["min_tier", "max_tier"])
def test_unknown_tier_name_is_rejected(tmp_path, key):
    path = _write(tmp_path, "calc", {"port": 9103, "llm": {"provider": "anthropic", key: "giant"}})
    with pytest.raises(AgentSpecError, match=f"llm.{key} must be one of: light, standard, heavy, extreme"):
        agent_spec.load_file(path)


def test_min_tier_above_max_tier_is_rejected(tmp_path):
    path = _write(tmp_path, "calc", {
        "port": 9103, "llm": {"provider": "anthropic", "min_tier": "heavy", "max_tier": "light"},
    })
    with pytest.raises(AgentSpecError, match="llm.min_tier 'heavy' is stronger than llm.max_tier 'light'"):
        agent_spec.load_file(path)


@pytest.mark.parametrize("key", ["min_tier", "max_tier"])
def test_laya_rejects_tier_bounds(tmp_path, key):
    path = _write(tmp_path, "triage", {"port": 9110, "llm": {"provider": "laya", key: "light"}})
    with pytest.raises(AgentSpecError, match="Laya triage does not accept"):
        agent_spec.load_file(path)


def test_default_gateway_per_provider():
    assert agent_spec.default_gateway("anthropic") == "claude"
    assert agent_spec.default_gateway("openai") == "gpt"
    assert agent_spec.default_gateway("laya") == "local"
    assert agent_spec.default_gateway("unknown") is None


def test_roster_entry_tiers_default_to_empty():
    assert agent_spec.RosterEntry("calc", "Calculator", "Math.").tiers == ()
    tier = agent_spec.TierInfo("light", "haiku", "quick")
    assert agent_spec.RosterEntry("calc", "Calculator", "Math.", (tier,)).tiers == (tier,)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (None, None),
        ("http://10.0.0.5:9103", "http://10.0.0.5:9103/mcp"),
        ("https://agents.example.com/calc/mcp/", "https://agents.example.com/calc/mcp"),
    ],
)
def test_url_is_normalised(tmp_path, given, expected):
    data = {"port": 9103, "llm": {"provider": "anthropic"}}
    if given is not None:
        data["url"] = given
    assert agent_spec.load_file(_write(tmp_path, "calc", data)).url == expected


@pytest.mark.parametrize("bad", ["10.0.0.5:9103", "ftp://host/mcp", "http://host/mcp?x=1", "http://host:99999/mcp"])
def test_bad_url_is_refused(tmp_path, bad):
    with pytest.raises(AgentSpecError, match="url"):
        agent_spec.load_file(_write(tmp_path, "calc", {"port": 9103, "url": bad, "llm": {"provider": "anthropic"}}))


def test_repository_agent_roster_is_valid():
    specs = agent_spec.load_dir(agent_spec.AGENTS_DIR)
    assert any(spec.entry and spec.enabled for spec in specs)


def test_app_monitor_has_existing_tools_without_stop_or_restart_access():
    app_dir = Path(__file__).resolve().parents[1]
    spec = agent_spec.load_file(app_dir / "agents" / "scheduler.json")
    tool_path = app_dir.parent / "armory" / "src" / "capabilities" / "server_manager" / "tool.py"
    names = [
        node.name for node in ast.parse(tool_path.read_text(encoding="utf-8")).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("tool_")
    ]
    ticket_tool_path = app_dir.parent / "armory" / "src" / "capabilities" / "tickets" / "tool.py"
    names.extend(
        node.name for node in ast.parse(ticket_tool_path.read_text(encoding="utf-8")).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("tool_")
    )

    assert spec.tools.unmatched(names) == []
    assert {name for name in names if spec.tools.allows(name)} == {
        "tool_srv_listApps", "tool_srv_startApp", "tool_ticket_createTicket",
    }
    assert not spec.tools.allows("tool_srv_stopApp")
    assert not spec.tools.allows("tool_srv_restartApp")


def test_reviewer_cannot_use_memory_tools_but_keeps_everything_else():
    app_dir = Path(__file__).resolve().parents[1]
    spec = agent_spec.load_file(app_dir / "agents" / "reviewer.json")
    tool_path = app_dir.parent / "armory" / "src" / "capabilities" / "memory" / "tool.py"
    memory_tools = [
        node.name for node in ast.parse(tool_path.read_text(encoding="utf-8")).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("tool_")
    ]

    assert memory_tools  # the real tool names, so a rename cannot silently defeat the deny glob
    assert not any(spec.tools.allows(name) for name in memory_tools)
    assert spec.tools.allow == ()  # still every other tool
    assert spec.tools.allows("tool_srv_listApps")


def test_memory_recall_defaults_to_false_and_loads_true(tmp_path):
    base = {"port": 9103, "llm": {"provider": "anthropic"}}
    assert agent_spec.load_file(_write(tmp_path, "calc", base)).memory_recall is False
    assert agent_spec.load_file(_write(tmp_path, "calc", {**base, "memory_recall": True})).memory_recall is True


def test_memory_recall_must_be_a_boolean(tmp_path):
    path = _write(tmp_path, "calc", {"port": 9103, "llm": {"provider": "anthropic"}, "memory_recall": "yes"})
    with pytest.raises(AgentSpecError, match="memory_recall"):
        agent_spec.load_file(path)


def test_laya_cannot_recall_memory(tmp_path):
    path = _write(tmp_path, "triage", {"port": 9110, "llm": {"provider": "laya"}, "tools": {"deny": ["*"]}, "memory_recall": True})
    with pytest.raises(AgentSpecError, match="memory_recall"):
        agent_spec.load_file(path)


def test_skill_recall_defaults_to_false_and_loads_true(tmp_path):
    base = {"port": 9103, "llm": {"provider": "anthropic"}}
    assert agent_spec.load_file(_write(tmp_path, "calc", base)).skill_recall is False
    assert agent_spec.load_file(_write(tmp_path, "calc", {**base, "skill_recall": True})).skill_recall is True


def test_skill_recall_must_be_a_boolean(tmp_path):
    path = _write(tmp_path, "calc", {"port": 9103, "llm": {"provider": "anthropic"}, "skill_recall": "yes"})
    with pytest.raises(AgentSpecError, match="skill_recall"):
        agent_spec.load_file(path)


def test_laya_cannot_recall_skills(tmp_path):
    path = _write(tmp_path, "triage", {"port": 9110, "llm": {"provider": "laya"}, "tools": {"deny": ["*"]}, "skill_recall": True})
    with pytest.raises(AgentSpecError, match="skill_recall"):
        agent_spec.load_file(path)


def test_no_tracked_agent_has_skill_recall_on_yet():
    specs = agent_spec.load_dir(agent_spec.AGENTS_DIR)
    assert [spec.id for spec in specs if spec.skill_recall] == []


def test_only_the_entry_agent_has_memory_recall_on():
    specs = {spec.id: spec for spec in agent_spec.load_dir(agent_spec.AGENTS_DIR)}
    assert specs["ember"].entry and specs["ember"].memory_recall is True
    assert [agent_id for agent_id, spec in specs.items() if spec.memory_recall] == ["ember"]


def test_an_override_replaces_the_tracked_file_and_can_add_an_agent(tmp_path):
    (tmp_path / "ember.json").write_text(json.dumps(
        {"port": 9100, "entry": True, "llm": {"provider": "anthropic"}}), encoding="utf-8")
    overrides = tmp_path / ".overrides"
    overrides.mkdir()
    (overrides / "agent_overrides.json").write_text(json.dumps({
        "ember": {"port": 9100, "entry": True, "llm": {"provider": "anthropic", "max_tier": "light"}},
        "calc": {"port": 9103, "llm": {"provider": "anthropic"}},
    }), encoding="utf-8")
    specs = {spec.id: spec for spec in agent_spec.load_dir(tmp_path)}
    assert specs["ember"].llm.max_tier == "light"
    assert "calc" in specs
    assert agent_spec.load_file(tmp_path / "calc.json").port == 9103


def test_delegable_defaults_to_true_and_loads_false(tmp_path):
    base = {"port": 9103, "llm": {"provider": "anthropic"}}
    assert agent_spec.load_file(_write(tmp_path, "calc", base)).delegable is True
    assert agent_spec.load_file(_write(tmp_path, "calc", {**base, "delegable": False})).delegable is False


def test_delegable_must_be_a_boolean(tmp_path):
    path = _write(tmp_path, "calc", {"port": 9103, "llm": {"provider": "anthropic"}, "delegable": "no"})
    with pytest.raises(AgentSpecError, match="delegable"):
        agent_spec.load_file(path)


def test_plan_tool_defaults_to_true_and_loads_false(tmp_path):
    base = {"port": 9103, "llm": {"provider": "anthropic"}}
    assert agent_spec.load_file(_write(tmp_path, "calc", base)).plan_tool is True
    assert agent_spec.load_file(_write(tmp_path, "calc", {**base, "plan_tool": False})).plan_tool is False


def test_plan_tool_must_be_a_boolean(tmp_path):
    path = _write(tmp_path, "calc", {"port": 9103, "llm": {"provider": "anthropic"}, "plan_tool": "no"})
    with pytest.raises(AgentSpecError, match="plan_tool"):
        agent_spec.load_file(path)
