"""Batch calls preserve order, independent validation, and bounded cancellation."""

from __future__ import annotations

import asyncio
import sys

import pytest

from src.capabilities.math.domain import MathDesk
from src.capabilities.math.utils.runner import ProcessRunner


def record(identifier, value):
    return {"id": identifier, "data": [{"type": "constant", "name": "x", "value": value}]}


@pytest.mark.asyncio
async def test_batch_preserves_order_and_isolates_invalid_record():
    runner = ProcessRunner()
    try:
        result = await MathDesk(runner).batch("y=2*x", [record("first", 2), record("bad", True), record("last", 5)])
        assert result.status == "partial"
        assert [row.id for row in result.records] == ["first", "bad", "last"]
        assert result.records[0].result.solutions[0].values["y"].exact == "4"
        assert result.records[1].result.status == "invalid"
        assert result.records[2].result.solutions[0].values["y"].exact == "10"
        assert result.success_count == 2
        assert result.failure_count == 1
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_batch_exposes_no_solution_per_record_without_aborting_others():
    runner = ProcessRunner()
    try:
        result = await MathDesk(runner).batch("x=2", [record("yes", 2), record("no", 3)])
        assert result.status == "completed"
        assert [row.result.status for row in result.records] == ["unique", "inconsistent"]
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_batch_accepts_units_and_structured_equation_controls():
    runner = ProcessRunner()
    try:
        result = await MathDesk(runner).batch({"expression": "y=x", "output_units": {"y": "cm"}}, [
            {"id": "metric", "data": [{"type": "constant", "name": "x", "value": 2, "unit": "m"}]},
        ])
        assert result.records[0].result.solutions[0].values["y"].exact == "200"
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_batch_limits_are_validated_before_spawning(monkeypatch):
    async def no_spawn(*args, **kwargs):
        pytest.fail("Invalid batch must not start a subprocess")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", no_spawn)
    desk = MathDesk()
    assert (await desk.batch("x=1", [])).status == "invalid"
    assert (await desk.batch("x=1", [record(str(i), i) for i in range(33)])).status == "invalid"
    assert (await desk.batch("x=1", [{"data": [], "extra": "x" * 270000}])).status == "limited"


@pytest.mark.asyncio
async def test_batch_uses_only_two_active_record_workers(monkeypatch):
    created = []
    original = asyncio.create_subprocess_exec

    async def observe(*args, **kwargs):
        process = await original(*args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", observe)
    runner = ProcessRunner()
    try:
        result = await MathDesk(runner).batch("y=x+1", [record(str(i), i) for i in range(6)])
        assert result.success_count == 6
        assert len(created) == 2
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_batch_deadline_reaps_active_work_and_labels_unfinished_records(monkeypatch):
    created = []
    original = asyncio.create_subprocess_exec

    async def observe(*args, **kwargs):
        process = await original(*args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", observe)
    runner = ProcessRunner(command=(sys.executable, "-c", "import sys,time; sys.stdin.read(); time.sleep(30)"))
    try:
        result = await MathDesk(runner, batch_timeout=0.3).batch("y=x", [record(str(i), i) for i in range(3)])
        assert result.status == "partial"
        assert all(row.result.status == "timeout" for row in result.records)
        assert created and all(process.returncode is not None for process in created)
    finally:
        await runner.close()
