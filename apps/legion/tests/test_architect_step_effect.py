"""Architect kind determines whether retrying an orchestrator step is safe."""

import asyncio

import pytest

from src.agents.roles.orchestrator import catalog, plan_runner, submit_plan


@pytest.mark.parametrize("kind,effect", [("code", "read"), ("operations", "write"),
                                       ("unknown", "write"), (None, "write")])
def test_plan_steps_run_once_with_kind_derived_effects(monkeypatch, kind, effect):
    snapshot = catalog.build([{"id": "architect", "role": "architect", "kind": kind, "focus": "Build"}])
    submitted, error = submit_plan.validate({"steps": [{"id": "s1", "architect": "architect",
        "brief": "A complete task brief for this architect.", "depends_on": []}]},
        snapshot.architect_ids, architect_kinds=snapshot.architect_kinds)
    assert error is None and submitted.steps[0].effect == effect
    tiers = []
    async def fail(node, tier, dependencies, **kwargs):
        tiers.append(tier)
        raise RuntimeError("failed")
    monkeypatch.setattr(plan_runner, "call_worker", fail)
    rows = asyncio.run(plan_runner.PlanSession(snapshot)._execute(submitted, 0, None, None))
    assert len(tiers) == 1
    assert rows["s1"].status == "failed"
    assert tiers == ["standard"]
