"""Native resource limits are installed only inside disposable child processes."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

from src.capabilities.math.contract import SolveRequest
from src.capabilities.math.utils.runner import ProcessRunner


@pytest.mark.asyncio
async def test_worker_reports_enforced_limits_and_peak_memory():
    runner = ProcessRunner()
    try:
        result = await runner.run(SolveRequest(equation="x=2", data=[]))
        resources = result["resources"]
        assert resources["hard_limits"] is True
        assert resources["enforcement"] in {"windows_job", "posix_rlimit"}
        assert 0 < resources["memory_limit_bytes"] <= 512 * 1024 * 1024
        assert resources["peak_memory_bytes"] > 0
        assert resources["cpu_seconds"] >= 0
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_small_child_memory_budget_refuses_larger_allocation():
    program = (
        "import json\n"
        "from src.capabilities.math.utils.resources import ResourceGuard\n"
        "guard=ResourceGuard(memory_bytes=64*1024*1024,cpu_seconds=3)\n"
        "guard.install()\n"
        "try:\n"
        " payload=bytearray(128*1024*1024)\n"
        " print(json.dumps({'limited':False}))\n"
        "except MemoryError:\n"
        " print(json.dumps({'limited':True,'enforcement':guard.enforcement}))\n"
    )
    child = await asyncio.create_subprocess_exec(sys.executable, "-c", program, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    async with asyncio.timeout(10):
        stdout, stderr = await child.communicate()
    assert child.returncode == 0, stderr.decode(errors="replace")
    assert json.loads(stdout)["limited"] is True


@pytest.mark.asyncio
async def test_aggregate_metrics_keep_bounded_durations_and_status_counts():
    runner = ProcessRunner()
    try:
        for number in (2, 3):
            await runner.run(SolveRequest(equation=f"x={number}", data=[]))
        metrics = runner.snapshot()
        assert metrics["calls"] == 2
        assert metrics["statuses"]["unique"] == 2
        assert metrics["worker_reuses"] == 1
        assert metrics["queue_ms"]["p95"] >= 0
        assert metrics["peak_memory_bytes"] > 0
        assert set(metrics) == {"calls", "statuses", "worker_reuses", "queue_ms", "total_ms", "peak_memory_bytes", "cpu_seconds", "window_size"}
    finally:
        await runner.close()
