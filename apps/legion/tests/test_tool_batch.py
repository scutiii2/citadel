import asyncio
import threading
import time

import pytest

from src.agents.roles.orchestrator import plan
from src.providers.turn_guard import TurnGuard, TurnStopped
from src.runtime import approvals, tool_batch
from src.runtime.tool_batch import Call, ToolRound

READ_ONLY = {"read_a", "read_b", "read_c"}


@pytest.fixture(autouse=True)
def read_only(monkeypatch):
    monkeypatch.setattr(tool_batch, "is_read_only_builtin", lambda name: name in READ_ONLY)


def make_round(dispatch, events=None, guard=None):
    used, records = [], []

    async def on_event(event):
        if events is not None:
            events.append(event)

    runner = ToolRound(guard=guard or TurnGuard(), dispatch=dispatch, labels={}, depth=0, request_id=None,
                       on_event=on_event, planning=None, checklist=plan.Checklist(), tools_used=used, tool_calls=records)
    return runner, used, records


def test_read_only_calls_run_at_the_same_time_and_results_keep_call_order():
    barrier = threading.Barrier(2, timeout=3)  # passes only when both calls are running together

    def dispatch(name, arguments, depth):
        barrier.wait()
        if name == "read_a":
            time.sleep(0.1)
        return f"{name} done"

    runner, used, records = make_round(dispatch)
    outcomes = asyncio.run(runner.run([Call("1", "read_a", {}), Call("2", "read_b", {})]))
    assert [o.text for o in outcomes] == ["read_a done", "read_b done"]
    assert used == ["read_a", "read_b"] and [r.name for r in records] == ["read_a", "read_b"]


def test_a_write_runs_alone_and_splits_the_reads_around_it():
    log, running = [], []
    lock = threading.Lock()

    def dispatch(name, arguments, depth):
        with lock:
            running.append(name)
            log.append(("start", name, len(running)))
        time.sleep(0.05)
        with lock:
            running.remove(name)
        return name

    runner, _, _ = make_round(dispatch)
    calls = [Call("1", "read_a", {}), Call("2", "write_x", {}), Call("3", "read_b", {}), Call("4", "read_c", {})]
    asyncio.run(runner.run(calls))
    starts = [entry for entry in log if entry[0] == "start"]
    assert [name for _, name, _ in starts] == ["read_a", "write_x", "read_b", "read_c"]
    assert dict((name, count) for _, name, count in starts)["write_x"] == 1  # nothing ran beside the write
    assert dict((name, count) for _, name, count in starts)["read_a"] == 1  # a lone read is not a group


def test_a_call_needing_approval_is_not_run_beside_others(monkeypatch):
    policy = approvals.ApprovalPolicy(mode="ask", allowed_tools={"read_a"})
    token = approvals.bind(policy)
    asked = []

    async def review(request_id, step_id, tool, label, arguments, on_event):
        if approvals.current().needs_approval(tool):
            asked.append(tool)
        return None

    monkeypatch.setattr(approvals, "review", review)
    peak, now, lock = [0], [0], threading.Lock()

    def dispatch(name, arguments, depth):
        with lock:
            now[0] += 1
            peak[0] = max(peak[0], now[0])
        time.sleep(0.05)
        with lock:
            now[0] -= 1
        return name

    try:
        runner, _, _ = make_round(dispatch)
        asyncio.run(runner.run([Call("1", "read_a", {}), Call("2", "read_b", {})]))
    finally:
        approvals.reset(token)
    assert asked == ["read_b"] and peak[0] == 1


def test_a_failing_call_is_reported_and_does_not_stop_its_neighbour():
    def dispatch(name, arguments, depth):
        if name == "read_a":
            raise RuntimeError("boom")
        return "fine"

    events = []
    runner, _, records = make_round(dispatch, events)
    outcomes = asyncio.run(runner.run([Call("1", "read_a", {}), Call("2", "read_b", {})]))
    assert [(o.text, o.ok) for o in outcomes] == [("Tool 'read_a' failed: boom", False), ("fine", True)]
    assert sorted(e["id"] for e in events if e["type"] == "step_start") == ["1", "2"]
    assert sorted(e["id"] for e in events if e["type"] == "step_end") == ["1", "2"]
    assert [r.result for r in records] == ["Tool 'read_a' failed: boom", "fine"]


def test_the_guard_stops_the_round_before_any_tool_runs():
    ran = []
    runner, used, _ = make_round(lambda *a: ran.append(a) or "x", guard=TurnGuard())
    same = [Call(str(i), "read_a", {"q": 1}) for i in range(3)]
    with pytest.raises(TurnStopped):
        asyncio.run(runner.run(same))
    assert ran == [] and used == []
