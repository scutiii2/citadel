"""Model plans and live catalog snapshots are untrusted input boundaries."""

import asyncio

import pytest

from src.agents import agent_registry
from src.agents.roles.orchestrator import catalog, submit_plan


def step(id="s1", **extra):
    return {"id": id, "architect": "code-architect", "brief": "Build the complete requested function.",
            "depends_on": [], **extra}


@pytest.mark.parametrize("raw,error", [
    (None, "steps"), ({"steps": []}, "steps"), ({"steps": [step()] * 9}, "8"),
    ({"steps": [step(), step()]}, "duplicate"),
    ({"steps": [step(architect="missing")]}, "architect"),
    ({"steps": [step(depends_on=["missing"])]}, "unknown"),
    ({"steps": [step(depends_on=["s1"])]}, "cycle"),
    ({"steps": [step(brief=" ")]}, "brief"), ({"steps": [step(brief="short")]}, "brief"),
    ({"steps": [step(brief=123)]}, "brief"), ({"steps": [step(id=[])]}, "id"),
    ({"steps": [step(architect=[])]}, "architect"),
    ({"steps": [step(depends_on="s1")]}, "depends_on"),
    ({"steps": [step(depends_on=[[]])]}, "depends_on"),
    ({"steps": [step(extra=1)]}, "extra"), ({"steps": [step()], "extra": 1}, "extra"),
    ({"steps": [None]}, "step"),
])
def test_invalid_submit_plan(raw, error):
    result, problem = submit_plan.validate(raw, {"code-architect"})
    assert result is None and error in problem


def test_valid_forward_dependencies_and_schema():
    raw = {"steps": [step("s1", depends_on=["s2"]), step("s2")]}
    result, problem = submit_plan.validate(raw, {"code-architect"})
    assert problem is None and result.steps[0].depends_on == ("s2",)
    schema = submit_plan.tool_parameters()
    assert schema["properties"]["steps"]["maxItems"] == 8
    assert schema["additionalProperties"] is False


def test_catalog_drops_workers_before_architects_and_enforces_hard_cap():
    agents = [{"id": "code-architect", "role": "architect", "kind": "code", "focus": "Build code",
               "workers": ["worker"]},
              {"id": "ops-architect", "role": "architect", "kind": "operations", "focus": "Run actions",
               "workers": ["worker"]},
              {"id": "worker", "role": "specialist", "focus": "Write functions"}]
    full = catalog.build(agents)
    assert "Write functions" in full.text and "code-architect" in full.text
    architect_only = catalog.build([dict(a, workers=[]) for a in agents])
    capped = catalog.build(agents, max_chars=len(architect_only.text))
    assert capped.architect_ids == frozenset({"code-architect", "ops-architect"})
    assert "Write functions" not in capped.text
    assert len(capped.text) <= len(architect_only.text)
    tiny = catalog.build(agents, max_chars=10)
    assert len(tiny.text) <= 10 and not tiny.architect_ids
    hostile = catalog.build([dict(agents[0], focus="a\nb" * 10000)])
    assert len(hostile.text) <= catalog.MAX_CHARS
    assert "\nb" not in hostile.text


def test_catalog_is_live_and_omits_blocked_agents(monkeypatch):
    from src.runtime import tool_filter
    async def exercise():
        agent_registry.register("architect", "Architect", "http://localhost:9130/mcp", role="architect",
                                focus="Build", kind="code", workers=["worker"])
        found = await catalog.for_turn()
        assert found.architect_ids == frozenset({"architect"})
        token = tool_filter.bind(["agent:architect"])
        try:
            assert not (await catalog.for_turn()).architect_ids
        finally:
            tool_filter.reset(token)
        agent_registry.deregister("architect")
        assert not (await catalog.for_turn()).architect_ids
    asyncio.run(exercise())
