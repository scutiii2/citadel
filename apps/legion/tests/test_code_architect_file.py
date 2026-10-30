"""The disabled CodeArchitect definition loads with the real agent directory."""

import json

from src.agents import agent_spec


def test_real_agents_include_disabled_code_architect():
    specs = agent_spec.load_dir(agent_spec.AGENTS_DIR)
    spec = next(spec for spec in specs if spec.id == "code-architect")
    assert not spec.enabled and not spec.entry and not spec.plan_tool
    assert spec.role == "architect" and spec.kind == "code"
    assert spec.workers == ("code-writer",) and spec.prefetch == ("repo-helper",)
    assert spec.limits == agent_spec.ArchitectLimits()
    assert spec.tools.deny == ("*",)
    assert spec.llm.provider == "anthropic" and spec.llm.gateway == "omniroute"
    assert spec.llm.model == "combo/heavy" and spec.focus
    assert not any(other.port == spec.port for other in specs if other.id != spec.id)
    raw = json.loads((agent_spec.AGENTS_DIR / "code-architect.json").read_text(encoding="utf-8"))
    assert raw["enabled"] is False
