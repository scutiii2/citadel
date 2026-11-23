"""TaskArchitect picks specialists from its workers list; canned completions, no network."""

import asyncio
import json
from dataclasses import replace

import pytest

from src.agents import agent_registry, agent_spec
from src.agents.roles.architect import pipeline, registry
from src.agents.roles.orchestrator import delegation
from src.providers.base_provider import ChatResult


def unit(id="a", agent="mathematician", **extra):
    return {"id": id, "agent": agent, "spec": f"Do {id}.", "depends_on": [], "effect": "read",
            "tier_hint": "light", **extra}


def plan(*units):
    return json.dumps({"units": list(units or [unit()])})


@pytest.fixture
def spec(monkeypatch):
    value = replace(agent_spec.current(), id="task-architect", role="architect", kind="task", entry=False,
                    workers=("mathematician", "researcher"), prefetch=(), plan_tool=False)
    monkeypatch.setattr(agent_spec, "_current", value)
    return value


def run(spec, responses, worker):
    responses, prompts = iter(responses), []
    def complete(prompt):
        prompts.append(prompt)
        return ChatResult(response=next(responses), total_tokens=15, input_tokens=10, output_tokens=5)
    delegation_call = delegation.call
    delegation.call = worker
    try:
        return asyncio.run(pipeline.run(spec, "brief", complete)), prompts
    finally:
        delegation.call = delegation_call


def test_registered_and_spec_accepts_the_kind():
    assert "task" in registry.KINDS and "task" in agent_spec.ARCHITECT_KINDS


def test_one_unit_returns_the_specialist_answer_without_assembly(spec):
    calls = []
    def worker(agent_id, question, depth, model_tier=None, reasoning_effort=None):
        calls.append((agent_id, question))
        return "42"
    result, prompts = run(spec, [plan()], worker)
    assert result.response == "42" and result.status == "done"
    assert calls == [("mathematician", "Do a.")] and len(prompts) == 1


def test_chain_passes_results_on_and_assembles(spec):
    calls = []
    def worker(agent_id, question, depth, model_tier=None, reasoning_effort=None):
        calls.append((agent_id, question))
        return "first result" if agent_id == "researcher" else "second result"
    nodes = plan(unit("a", "researcher"), unit("b", depends_on=["a"]))
    result, prompts = run(spec, [nodes, "final reply"], worker)
    assert result.response == "final reply" and len(prompts) == 2
    assert calls[1][0] == "mathematician" and "first result" in calls[1][1]


@pytest.mark.parametrize("bad,message", [
    (plan(unit(agent="server-ops")), "must be one of"),
    (json.dumps({"units": [{**unit(), "extra": 1}]}), "unknown or missing field"),
    (plan(unit(effect="maybe")), "effect must be read or write"),
    (plan(unit(depends_on=["missing"])), "unknown dependency"),
    ("not json", "Invalid plan JSON"),
])
def test_invalid_plans_are_refused(spec, bad, message):
    with pytest.raises(ValueError, match=message):
        registry.KINDS["task"].parse_plan(bad, spec)


def test_plan_prompt_lists_only_registered_workers(monkeypatch, spec):
    monkeypatch.setattr(agent_registry, "get_agent",
                        lambda key: {"focus": f"{key} focus"} if key == "mathematician" else None)
    prompt = registry.KINDS["task"].plan_prompt("2+2", "", spec)
    assert "mathematician focus" in prompt and "researcher" not in prompt


from src.agents.roles.architect.types import NodeResult


def kind_spec(spec, kind, *workers):
    return replace(spec, kind=kind, workers=workers)


@pytest.mark.parametrize("kind,workers,good,bad", [
    ("review", ("mathematician", "researcher", "reviewer"),
     [unit("a", "researcher"), unit("b", "researcher"), unit("c", "reviewer", depends_on=["a", "b"])],
     [unit("a", "researcher")]),
    ("review", ("mathematician", "reviewer"),
     [unit("a"), unit("b", "reviewer", depends_on=["a"])],
     [unit("a", "reviewer")]),
    ("writing", ("researcher", "mathematician"),
     [unit("o"), unit("s1", depends_on=["o"]), unit("s2", depends_on=["o"])],
     [unit("o"), unit("s1", depends_on=["o"]), unit("s2")]),
    ("operations", ("researcher", "mathematician"),
     [unit("r"), unit("w", effect="write", depends_on=["r"]), unit("v", depends_on=["w"])],
     [unit("r"), unit("w", effect="write", depends_on=["r"])]),
])
def test_kind_rules_accept_a_good_plan_and_refuse_a_bad_one(spec, kind, workers, good, bad):
    handler, current = registry.KINDS[kind], kind_spec(spec, kind, *workers)
    assert len(handler.parse_plan(plan(*good), current).units) == len(good)
    with pytest.raises(ValueError):
        handler.parse_plan(plan(*bad), current)


def test_operations_refuses_a_write_with_no_read_before_it(spec):
    current = kind_spec(spec, "operations", "mathematician")
    with pytest.raises(ValueError, match="depend on a read unit"):
        registry.KINDS["operations"].parse_plan(plan(unit("w", effect="write")), current)


def test_data_flags_figures_no_specialist_produced(spec):
    handler = registry.KINDS["task"]
    results = {"a": NodeResult("done", output="The total is 1,250 across 8 rows.")}
    kept, _ = handler.review_assembly("Total 1250 over 8 rows.", None, "sum the table", results)
    assert "Figures not found" not in kept
    flagged, _ = handler.review_assembly("Total 9999 over 8 rows.", None, "sum the table", results)
    assert "Figures not found in any specialist result" in flagged and "9999" in flagged and "1250" not in flagged.split("result")[-1]
