"""Shared DAG execution uses fake async workers, never a model or network."""

import asyncio
import threading

import pytest

from src.agents import agent_events
from src.agents.agent_spec import ArchitectLimits
from src.agents.roles.architect.executor import DagExecutor, call_worker, validate_dag
from src.agents.roles.architect.types import NodeResult, Unit
from src.agents.roles.orchestrator import delegation
from src.providers import cancellation
from src.providers.base_provider import ChatCancelled


@pytest.mark.parametrize("nodes,error", [
    ([Unit("a", "one"), Unit("a", "two")], "duplicate"),
    ([Unit("a", "one", depends_on=("missing",))], "unknown"),
    ([Unit("a", "one", depends_on=("a",))], "cycle"),
    ([Unit("a", "one", depends_on=("b",)), Unit("b", "two", depends_on=("a",))], "cycle"),
])
def test_validate_before_running(nodes, error):
    async def run(*_):
        pytest.fail("invalid DAG executed")
    with pytest.raises(ValueError, match=error):
        asyncio.run(DagExecutor().run(nodes, run))


def test_waves_and_parallel_cap():
    async def exercise():
        active = maximum = 0
        started, finished = [], []
        async def run(node, tier, dependencies):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            started.append((node.id, set(finished)))
            assert all(result.status == "done" for result in dependencies.values())
            await asyncio.sleep(0.01 if node.id == "a" else 0.02)
            active -= 1
            finished.append(node.id)
            return node.id
        nodes = [Unit("a", "one"), Unit("b", "two"), Unit("c", "three"),
                 Unit("d", "four", depends_on=("a",))]
        result = await DagExecutor(ArchitectLimits(max_parallel=2)).run(nodes, run)
        assert maximum == 2
        assert started[-1] == ("d", {"a", "b", "c"})
        assert all(row.status == "done" for row in result.values())
    asyncio.run(exercise())


def test_retries_escalate_and_record_all_attempts_once():
    async def exercise():
        attempts, events = [], []
        usage, usage_token = delegation.bind_usage()
        token = agent_events.bind(events.append, "dag")
        async def run(node, tier, dependencies):
            attempts.append(tier)
            return NodeResult("done" if tier == "heavy" else "failed", output=tier,
                              error=None if tier == "heavy" else "try again",
                              agent_usage=[{"model": tier, "request_id": "child", "delegated_by": "parent"}])
        try:
            result = await DagExecutor(ArchitectLimits(max_retries=3)).run(
                [Unit("a", "one", agent_id="worker", tier_hint="light")], run)
            assert result["a"].output == "heavy"
            assert attempts == ["light", "standard", "heavy"]
            assert [row["model"] for row in usage] == attempts
            assert all(row["request_id"] == "child" and row["delegated_by"] == "parent" for row in usage)
            assert [e["type"] for e in events] == ["agent_start", "agent_end"] * 3
            assert all(e["agent_id"] == "worker" for e in events)
        finally:
            agent_events.reset(token)
            delegation.reset_usage(usage_token)
    asyncio.run(exercise())


def test_write_is_never_retried_and_failure_skips_transitive_dependents():
    async def exercise():
        attempts = []
        async def run(node, tier, dependencies):
            attempts.append(node.id)
            if node.id == "write":
                raise RuntimeError("send failed")
            return "ok"
        nodes = [Unit("write", "send", effect="write"), Unit("b", "then", depends_on=("write",)),
                 Unit("c", "last", depends_on=("b",)), Unit("independent", "safe")]
        results = await DagExecutor(ArchitectLimits(max_retries=5)).run(nodes, run)
        assert attempts == ["write", "independent"]
        assert [results[n.id].status for n in nodes] == ["failed", "skipped", "skipped", "done"]
        assert results["write"].error == "send failed"
    asyncio.run(exercise())


def test_timeout_fails_node():
    async def run(*_):
        await asyncio.sleep(10)
    rows = asyncio.run(DagExecutor(ArchitectLimits(unit_timeout_seconds=0.01, max_retries=0)).run([Unit("a", "slow")], run))
    assert rows["a"].status == "failed" and "timed out" in rows["a"].error


def test_timeout_can_retry_read_with_fresh_child_cancellation():
    async def exercise():
        attempts = []
        async def run(node, tier, dependencies):
            attempts.append(cancellation.current_request_id())
            if len(attempts) == 1:
                await asyncio.sleep(10)
            assert not cancellation.is_cancelled(cancellation.current_request_id())
            return "ok"
        rows = await DagExecutor(ArchitectLimits(unit_timeout_seconds=0.01)).run([Unit("a", "slow")], run)
        assert rows["a"].status == "done" and len(set(attempts)) == 2
    asyncio.run(exercise())


def test_cancel_before_start_and_while_waiting():
    async def exercise(pre_cancel):
        request_id = "dag-cancel"
        token = cancellation.bind_request(request_id)
        started = asyncio.Event()
        stopped = []
        async def run(node, tier, dependencies):
            started.set()
            try:
                await asyncio.sleep(10)
            finally:
                stopped.append(node.id)
        try:
            if pre_cancel:
                cancellation.cancel(request_id)
            task = asyncio.create_task(DagExecutor(ArchitectLimits(max_parallel=1)).run(
                [Unit("a", "slow"), Unit("b", "queued"), Unit("c", "dependent", depends_on=("a",))],
                run, request_id))
            if not pre_cancel:
                await started.wait()
                cancellation.cancel(request_id)
            rows = await asyncio.wait_for(task, 1)
            assert all(row.status == "cancelled" for row in rows.values())
            assert stopped == ([] if pre_cancel else ["a"])
        finally:
            cancellation.clear(request_id)
            cancellation.reset_request(token)
    asyncio.run(exercise(True))
    asyncio.run(exercise(False))


def test_chat_cancelled_is_not_retried():
    attempts = []
    async def run(*_):
        attempts.append(1)
        raise ChatCancelled()
    rows = asyncio.run(DagExecutor().run([Unit("a", "cancel")], run))
    assert rows["a"].status == "cancelled" and len(attempts) == 1


def test_real_worker_runs_in_thread_with_dependency_context_and_no_duplicate_usage(monkeypatch):
    thread_id = threading.get_ident()
    calls = []
    def fake(agent_id, question, depth, model_tier=None, reasoning_effort=None):
        assert threading.get_ident() != thread_id
        assert cancellation.current_request_id() == "parent"
        calls.append((agent_id, question, depth, model_tier, reasoning_effort))
        delegation.record_usage([{"agent_id": agent_id}])
        return "body"
    monkeypatch.setattr(delegation, "call", fake)
    async def exercise():
        token = cancellation.bind_request("parent")
        usage, usage_token = delegation.bind_usage()
        try:
            node = Unit("b", "build", depends_on=("a",), needs_body_of=("a",), agent_id="worker",
                        reasoning_effort="high")
            rows = {"a": NodeResult("done", output="dependency body")}
            result = await call_worker(node, "heavy", rows, depth=1)
            assert result.output == "body" and usage == [{"agent_id": "worker"}]
            assert calls[0][0] == "worker" and "dependency body" in calls[0][1]
            assert calls[0][2:] == (1, "heavy", "high")
        finally:
            delegation.reset_usage(usage_token)
            cancellation.clear("parent")
            cancellation.reset_request(token)
    asyncio.run(exercise())
