"""Architect kind determines whether retrying an orchestrator step is safe."""

import asyncio

import pytest

from src.agents.agent_spec import ArchitectLimits
from src.agents.roles.architect.executor import DagExecutor
from src.agents.roles.orchestrator import catalog, submit_plan


@pytest.mark.parametrize("kind,effect,attempts", [("code", "read", 2), ("operations", "write", 1),
                                               ("unknown", "write", 1), (None, "write", 1)])
def test_step_effect_and_retry_exhaustion(kind, effect, attempts):
    snapshot = catalog.build([{"id": "architect", "role": "architect", "kind": kind, "focus": "Build"}])
    submitted, error = submit_plan.validate({"steps": [{"id": "s1", "architect": "architect",
        "brief": "A complete task brief for this architect.", "depends_on": []}]},
        snapshot.architect_ids, architect_kinds=snapshot.architect_kinds)
    assert error is None and submitted.steps[0].effect == effect
    tiers = []
    async def fail(node, tier, dependencies):
        tiers.append(tier)
        raise RuntimeError("failed")
    rows = asyncio.run(DagExecutor(ArchitectLimits()).run(submitted.steps, fail))
    assert len(tiers) == attempts
    assert rows["s1"].status == "failed"
    assert tiers == (["standard", "heavy"] if kind == "code" else ["standard"])
