"""Whole architect steps have more time than individual pipeline units."""

import asyncio

from src.agents.agent_spec import ArchitectLimits
from src.agents.roles.architect.types import NodeResult, Plan, Step
from src.agents.roles.orchestrator import catalog, plan_runner


def test_plan_step_timeout_is_separate_from_architect_unit_timeout(monkeypatch):
    async def exercise(seconds):
        loop = asyncio.get_running_loop()
        now = [loop.time()]
        calls = []

        async def fake_sleep(delay):
            now[0] += delay
            for _ in range(3):
                await asyncio.sleep(0)

        async def worker(*args, **kwargs):
            calls.append(seconds)
            await fake_sleep(seconds)
            return NodeResult("done", output="assembled")

        with monkeypatch.context() as patch:
            patch.setattr(loop, "time", lambda: now[0])
            patch.setattr(plan_runner, "call_worker", worker)
            session = plan_runner.PlanSession(catalog.Catalog("", frozenset({"code-architect"})))
            submitted = Plan((Step("s1", "code-architect", "Build the requested functions.", effect="read"),))
            results = await session._execute(submitted, 0, None, None)
        assert calls == [seconds]
        return results["s1"]

    assert ArchitectLimits().unit_timeout_seconds == 120
    completed = asyncio.run(exercise(180))
    assert completed.status == "done" and completed.output == "assembled"
    expired = asyncio.run(exercise(271))
    assert expired.status == "failed" and expired.error == "node timed out"
    assert plan_runner.PLAN_STEP_TIMEOUT_SECONDS == 270
    assert ArchitectLimits().unit_timeout_seconds == 120
