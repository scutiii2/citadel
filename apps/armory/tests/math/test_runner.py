"""Real subprocess coverage for deadlines, cancellation, and bounded execution."""

from __future__ import annotations

import asyncio
import sys

import pytest

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.domain import MathDesk
from src.capabilities.math.utils.runner import ProcessRunner


@pytest.mark.asyncio
async def test_real_worker_solves_complex_equation():
    result = await MathDesk().solve("x^2 = -1", [])
    assert result.status == "multiple"
    assert {row.values["x"].exact for row in result.solutions} == {"I", "-I"}


@pytest.mark.asyncio
async def test_simultaneous_calls_do_not_block_event_loop():
    desk = MathDesk()
    pending = [asyncio.create_task(desk.solve(f"x = {value}", [])) for value in (2, 3, 4)]
    ticks = 0
    while any(not task.done() for task in pending):
        ticks += 1
        await asyncio.sleep(0.01)
    results = await asyncio.gather(*pending)
    assert [result.solutions[0].values["x"].exact for result in results] == ["2", "3", "4"]
    assert ticks > 2


@pytest.fixture
def children(monkeypatch):
    """Observe real children without replacing their I/O or lifecycle."""
    created = []
    original = asyncio.create_subprocess_exec

    async def spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    return created


@pytest.mark.asyncio
async def test_timeout_reaps_worker_and_next_request_can_run(children):
    runner = ProcessRunner(command=(sys.executable, "-c", "import time; time.sleep(30)"), timeout=0.2)
    result = await runner.run(SolveRequest(equation="1+1", data=[]))
    assert result["status"] == "timeout"
    assert children and all(child.returncode is not None for child in children)
    # Same runner retains its slot capacity after a terminated calculation.
    result = await runner.run(SolveRequest(equation="2+2", data=[]))
    assert result["status"] == "timeout"
    assert len(children) == 2
    assert all(child.returncode is not None for child in children)


@pytest.mark.asyncio
async def test_cancellation_reaps_child_before_propagating(children):
    runner = ProcessRunner(command=(sys.executable, "-c", "import time; time.sleep(30)"))
    task = asyncio.create_task(runner.run(SolveRequest(equation="1", data=[])))
    async with asyncio.timeout(5):
        while not children:
            await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[0].returncode is not None


@pytest.mark.asyncio
async def test_concurrency_and_admission_are_bounded(children):
    runner = ProcessRunner(command=(sys.executable, "-c", "import time; time.sleep(30)"),
                           max_workers=1, max_pending=2, timeout=0.3)
    request = SolveRequest(equation="1", data=[])
    results = await asyncio.gather(*(runner.run(request) for _ in range(3)))
    assert sorted(result["status"] for result in results) == ["limited", "timeout", "timeout"]
    assert len(children) == 1
    assert children[0].returncode is not None


@pytest.mark.asyncio
async def test_oversized_worker_output_is_stopped(children):
    runner = ProcessRunner(command=(sys.executable, "-c", "import sys; sys.stdin.read(); print('x' * 300000)"))
    result = await runner.run(SolveRequest(equation="1", data=[]))
    assert result["status"] == "limited"
    assert children[0].returncode is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("program", ["print('invalid JSON')", "raise SystemExit(1)"])
async def test_worker_failure_is_structured(program):
    runner = ProcessRunner(command=(sys.executable, "-c", program))
    result = await runner.run(SolveRequest(equation="1", data=[]))
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_bad_request_returns_validation_result_before_spawning(children):
    result = await MathDesk().solve("x", [{"type": "constant", "name": "x", "value": True}])
    assert result.status == "invalid"
    assert children == []
