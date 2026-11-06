"""Reusable workers retain bounds, isolation, and reliable lifecycle cleanup."""

from __future__ import annotations

import asyncio
import sys

import pytest
from starlette.applications import Starlette

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.domain import MathDesk
from src.capabilities.math.utils.runner import ProcessRunner


@pytest.fixture
def children(monkeypatch):
    created = []
    original = asyncio.create_subprocess_exec

    async def spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    return created


@pytest.mark.asyncio
async def test_sequential_calculations_reuse_worker_and_report_phase_timings(children):
    runner = ProcessRunner(reuse_workers=True)
    try:
        first = await runner.run(SolveRequest(equation="x^2=-1", data=[]))
        second = await runner.run(SolveRequest(equation="y=3", data=[]))
        assert len(children) == 1
        assert first["execution"]["worker_reused"] is False
        assert second["execution"]["worker_reused"] is True
        assert second["execution"]["worker_request"] == 2
        assert second["timings"]["startup_ms"] == 0
        assert first["timings"]["startup_ms"] > 0
        assert all(second["timings"][name] >= 0 for name in ("queue_ms", "parse_ms", "solve_ms", "verification_ms", "total_ms"))
        assert second["solutions"][0]["verification"]["status"] == "exact"
    finally:
        await runner.close()
    assert all(child.returncode is not None for child in children)


@pytest.mark.asyncio
async def test_reuse_does_not_share_bindings_between_requests():
    runner = ProcessRunner(reuse_workers=True)
    try:
        desk = MathDesk(runner)
        first = await desk.solve("y=x", [{"type": "constant", "name": "x", "value": 7}])
        second = await desk.solve("y=x", [])
        assert first.solutions[0].values["y"].exact == "7"
        assert second.status == "parametric"
        assert second.solutions[0].values["y"].exact == "x"
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_worker_is_recycled_after_request_budget(children):
    runner = ProcessRunner(reuse_workers=True, max_requests=2)
    try:
        results = [await runner.run(SolveRequest(equation="x=1", data=[])) for _ in range(3)]
        assert [result["execution"]["worker_request"] for result in results] == [1, 2, 1]
        assert len(children) == 2
        assert children[0].returncode is not None
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_idle_worker_expires_and_next_request_starts_new_child(children):
    runner = ProcessRunner(reuse_workers=True, idle_timeout=0.05)
    try:
        request = SolveRequest(equation="x=1", data=[])
        await runner.run(request)
        async with asyncio.timeout(5):
            await children[0].wait()
        assert children[0].returncode is not None
        result = await runner.run(request)
        assert len(children) == 2
        assert result["execution"]["worker_reused"] is False
    finally:
        await runner.close()


def framed_command():
    program = (
        "import json,sys,time\n"
        "print(json.dumps({'ready':True,'initialization_ms':0}),flush=True)\n"
        "for line in sys.stdin:\n"
        " request=json.loads(line)\n"
        " if request['equation']=='sleep': time.sleep(30)\n"
        " print(json.dumps({'status':'unique','message':'ok','future_field':{'kept':True}}),flush=True)\n"
    )
    return sys.executable, "-u", "-c", program


@pytest.mark.asyncio
async def test_timeout_retires_reused_worker_and_replacement_recovers(children):
    runner = ProcessRunner(command=framed_command(), reuse_workers=True, timeout=0.3)
    try:
        normal = SolveRequest(equation="1", data=[])
        assert (await runner.run(normal))["future_field"] == {"kept": True}
        result = await runner.run(SolveRequest(equation="sleep", data=[]))
        assert result["status"] == "timeout"
        assert children[0].returncode is not None
        result = await runner.run(normal)
        assert result["status"] == "unique"
        assert len(children) == 2
        assert result["execution"]["worker_reused"] is False
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_cancellation_retires_active_reused_worker(children):
    runner = ProcessRunner(command=framed_command(), reuse_workers=True)
    try:
        await runner.run(SolveRequest(equation="1", data=[]))
        task = asyncio.create_task(runner.run(SolveRequest(equation="sleep", data=[])))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert children[0].returncode is not None
        assert (await runner.run(SolveRequest(equation="1", data=[])))["status"] == "unique"
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_capability_lifespan_reaps_idle_workers(children, monkeypatch):
    from src.capabilities.math import CAPABILITY
    from src.capabilities.math.utils import runner as runtime

    runner = ProcessRunner(reuse_workers=True)
    monkeypatch.setattr(runtime, "runner", runner)
    application = Starlette()
    CAPABILITY.install_routes(application)
    async with application.router.lifespan_context(application):
        await runner.run(SolveRequest(equation="x=1", data=[]))
        assert children[0].returncode is None
    assert children[0].returncode is not None


@pytest.mark.asyncio
async def test_cancel_during_spawn_drains_full_stdout_before_reaping(monkeypatch):
    original = asyncio.create_subprocess_exec
    created = []
    ready = asyncio.Event()

    async def delayed_spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        created.append(process)
        ready.set()
        await asyncio.sleep(0.2)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    command = (sys.executable, "-u", "-c", "import sys,time; sys.stdout.write('x'*1500000); sys.stdout.flush(); time.sleep(30)")
    runner = ProcessRunner(command=command)
    task = asyncio.create_task(runner.run(SolveRequest(equation="1", data=[])))
    await ready.wait()
    await asyncio.sleep(0.1)
    task.cancel()
    done, pending = await asyncio.wait({task}, timeout=2)
    if pending:
        # Break the reproduced transport deadlock so a failing test leaves no child.
        await created[0].stdout.read()
        await asyncio.gather(task, return_exceptions=True)
    assert not pending, "Cancellation hung while reaping a child with a full stdout pipe"
    assert task.cancelled()
    assert created[0].returncode is not None
    await runner.close()


@pytest.mark.asyncio
async def test_close_coordinates_active_one_shot_reader(children):
    runner = ProcessRunner(command=(sys.executable, "-u", "-c", "import sys,time; sys.stdin.read(); time.sleep(30)"))
    task = asyncio.create_task(runner.run(SolveRequest(equation="1", data=[])))
    async with asyncio.timeout(5):
        while not children:
            await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    try:
        await runner.close()
    finally:
        await asyncio.gather(task, return_exceptions=True)
    assert children[0].returncode is not None
