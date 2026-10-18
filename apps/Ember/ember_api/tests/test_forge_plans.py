from __future__ import annotations

from pathlib import Path

import pytest

from src.services.forge.plans import InvalidPlanList, PlanPolicyRegistry, normalize_plan
from tests.forge_support import run


def test_the_allowlist_starts_empty_so_every_plan_is_refused(tmp_path: Path) -> None:
    async def scenario(env):
        worker = await env.add_worker(plan="Max")
        async with env.database.sessions() as session:
            registry = PlanPolicyRegistry(session)
            assert await registry.allowed() == {"claude": [], "codex": []}
            assert await registry.problem(worker) == "Plan not eligible: Max"

    run(tmp_path, scenario)


def test_an_allowed_plan_passes_ignoring_case_and_spaces(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", " Max  5x ", "pro")
        worker = await env.add_worker(plan="max 5X")
        async with env.database.sessions() as session:
            registry = PlanPolicyRegistry(session)
            assert await registry.allowed() == {"claude": ["max 5x", "pro"], "codex": []}
            assert await registry.problem(worker) is None

    run(tmp_path, scenario)


def test_each_provider_has_its_own_list(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        codex = await env.add_worker(provider="codex", plan="max")
        async with env.database.sessions() as session:
            assert await PlanPolicyRegistry(session).problem(codex) == "Plan not eligible: max"

    run(tmp_path, scenario)


def test_a_worker_that_has_not_reported_a_plan_is_refused(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(plan=None)
        async with env.database.sessions() as session:
            assert await PlanPolicyRegistry(session).problem(worker) == "Plan not eligible: not reported yet"

    run(tmp_path, scenario)


def test_the_list_is_cleaned_and_limited(tmp_path: Path) -> None:
    async def scenario(env):
        async with env.database.sessions() as session:
            policy = PlanPolicyRegistry(session).for_provider("claude")
            assert await policy.set_allowed(["Max", "max", "  ", "Pro"]) == ["max", "pro"]
            with pytest.raises(InvalidPlanList):
                await policy.set_allowed([f"plan{i}" for i in range(13)])
            with pytest.raises(InvalidPlanList):
                await policy.set_allowed(["x" * 41])

    run(tmp_path, scenario)


def test_normalize_plan() -> None:
    assert normalize_plan("  Max   5X ") == "max 5x"
