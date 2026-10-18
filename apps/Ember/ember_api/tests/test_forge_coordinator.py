from __future__ import annotations

from pathlib import Path

import pytest

from src.services.forge.connections import WorkerConnection, WorkerRegistry
from src.services.forge.coordinator import GroupBusy, TurnCoordinator
from src.services.forge.events import GroupEventBus
from src.services.forge.groups import GroupNotFound
from src.services.forge.messages import MessageStore
from src.services.forge.protocol import (
    Delta,
    PermissionRequested,
    ToolUsed,
    TurnDone,
    TurnError,
    Usage,
)
from src.services.forge.routing import TurnRouter
from tests.forge_support import FakeTransport, run, settle, settle_async


async def _last_kind(store, group, kind: str) -> bool:
    messages = await store.list_after(group.id)
    return bool(messages) and messages[-1].kind == kind


def build(env, **kwargs):
    registry, bus, store = WorkerRegistry(), GroupEventBus(), MessageStore(env.database)
    coordinator = TurnCoordinator(env.database, registry, bus, store, TurnRouter(), **kwargs)
    return coordinator, registry, bus, store


def connect(registry, worker) -> FakeTransport:
    transport = FakeTransport()
    registry.register(WorkerConnection(worker.id, transport))
    return transport


async def kinds(store, group) -> list[tuple[str, str]]:
    return [(m.sender, m.kind) for m in await store.list_after(group.id)]


def test_a_turn_runs_and_the_reply_is_stored(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, bus, store = build(env)
        transport = connect(registry, worker)

        message = await coordinator.post_user_message(1, group.id, "@claude fix it")
        assert message.seq == 1 and coordinator.is_running(group.id)
        await settle(lambda: transport.sent)
        frame = transport.sent[0]
        assert (frame["type"], frame["prompt"], frame["folder"], frame["mode"]) == ("turn", "@claude fix it", "C:/work", "ask")
        assert frame["history"] == [] and frame["group_id"] == group.id

        await coordinator.on_worker_frame(worker.id, Usage(turn_id=frame["turn_id"], input_tokens=5, output_tokens=7))
        await coordinator.on_worker_frame(worker.id, TurnDone(turn_id=frame["turn_id"], text="Done"))
        await settle(lambda: not coordinator.is_running(group.id))

        assert await kinds(store, group) == [("user", "text"), (str(worker.id), "text")]
        reply = (await store.list_after(group.id))[1]
        assert reply.body == {
            "text": "Done", "label": "claude", "provider": "claude", "turn_id": frame["turn_id"],
            "usage": {"input_tokens": 5, "output_tokens": 7},
        }

    run(tmp_path, scenario)


def test_deltas_tools_and_state_reach_the_browser_bus(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, bus, store = build(env)
        transport = connect(registry, worker)
        events = bus.subscribe(group.id).events(ping_seconds=5)

        await coordinator.post_user_message(1, group.id, "@claude go")
        await settle(lambda: transport.sent)
        turn_id = transport.sent[0]["turn_id"]
        await coordinator.on_worker_frame(worker.id, Delta(turn_id=turn_id, text="Hel"))
        await coordinator.on_worker_frame(worker.id, ToolUsed(turn_id=turn_id, name="Edit", summary="a.py"))
        await coordinator.on_worker_frame(worker.id, TurnDone(turn_id=turn_id, text="Hello"))
        await settle(lambda: not coordinator.is_running(group.id))

        # In order: the user's message, turn on, the delta, the tool row, the reply, turn off.
        seen = [await anext(events) for _ in range(6)]
        assert [(e["type"], e.get("kind", e.get("running"))) for e in seen if e["type"] != "delta"] == [
            ("message", "text"), ("turn", True), ("message", "tool"), ("message", "text"), ("turn", False),
        ]
        delta = next(e for e in seen if e["type"] == "delta")
        assert (delta["text"], delta["label"], delta["sender"]) == ("Hel", "claude", str(worker.id))

    run(tmp_path, scenario)


def test_a_message_while_a_turn_runs_is_refused(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, _bus, _store = build(env)
        transport = connect(registry, worker)

        await coordinator.post_user_message(1, group.id, "@claude one")
        with pytest.raises(GroupBusy):
            await coordinator.post_user_message(1, group.id, "@claude two")
        await settle(lambda: transport.sent)
        await coordinator.on_worker_frame(worker.id, TurnDone(turn_id=transport.sent[0]["turn_id"], text="ok"))
        await settle(lambda: not coordinator.is_running(group.id))
        await coordinator.post_user_message(1, group.id, "@claude three")  # free again
        await coordinator.shutdown()

    run(tmp_path, scenario)


def test_another_accounts_group_looks_missing(tmp_path: Path) -> None:
    async def scenario(env):
        group = await env.add_group(account_id=2)
        coordinator, _registry, _bus, _store = build(env)

        with pytest.raises(GroupNotFound):
            await coordinator.post_user_message(1, group.id, "@claude hi")
        assert not coordinator.is_running(group.id)  # the claim was released

    run(tmp_path, scenario)


def test_a_message_with_no_target_gets_a_hint_and_starts_no_turn(tmp_path: Path) -> None:
    async def scenario(env):
        a, b = await env.add_worker(label="a"), await env.add_worker(label="b")
        group = await env.add_group(workers=[a, b])
        coordinator, _registry, _bus, store = build(env)

        await coordinator.post_user_message(1, group.id, "hello?")

        assert not coordinator.is_running(group.id)
        messages = await store.list_after(group.id)
        assert [(m.sender, m.kind) for m in messages] == [("user", "text"), ("system", "system")]
        assert "@label" in messages[1].body["text"]

    run(tmp_path, scenario)


def test_an_offline_worker_gets_a_system_message(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, _registry, _bus, store = build(env)

        await coordinator.post_user_message(1, group.id, "@claude hi")
        await settle(lambda: not coordinator.is_running(group.id))

        last = (await store.list_after(group.id))[-1]
        assert (last.sender, last.kind) == ("system", "system")
        assert last.body["text"].startswith("@claude is offline")

    run(tmp_path, scenario)


def test_a_plan_that_stopped_being_eligible_fails_the_turn(tmp_path: Path) -> None:
    async def scenario(env):
        worker = await env.add_worker(label="claude", plan="Free")  # the allowlist is empty
        group = await env.add_group(workers=[worker])
        coordinator, registry, _bus, store = build(env)
        transport = connect(registry, worker)

        await coordinator.post_user_message(1, group.id, "@claude hi")
        await settle(lambda: not coordinator.is_running(group.id))

        assert transport.sent == []
        assert "Plan not eligible: Free" in (await store.list_after(group.id))[-1].body["text"]

    run(tmp_path, scenario)


def test_a_worker_error_is_reported_and_the_cursor_does_not_move(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, _bus, store = build(env)
        transport = connect(registry, worker)

        await coordinator.post_user_message(1, group.id, "@claude hi")
        await settle(lambda: transport.sent)
        await coordinator.on_worker_frame(worker.id, TurnError(turn_id=transport.sent[0]["turn_id"], message="not logged in"))
        await settle(lambda: not coordinator.is_running(group.id))

        assert (await store.list_after(group.id))[-1].body["text"] == "@claude failed: not logged in"
        from src.services.forge.groups import GroupService
        from src.services.forge.plans import PlanPolicyRegistry

        async with env.database.sessions() as session:
            member = await GroupService(session, 1, PlanPolicyRegistry(session)).member(group.id, worker.id)
            assert member.last_seq == 0

    run(tmp_path, scenario)


def test_a_dropped_worker_fails_its_turn(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, _bus, store = build(env)
        transport = connect(registry, worker)

        await coordinator.post_user_message(1, group.id, "@claude hi")
        await settle(lambda: transport.sent)
        await coordinator.on_worker_disconnected(worker.id)
        await settle(lambda: not coordinator.is_running(group.id))

        assert (await store.list_after(group.id))[-1].body["text"] == "@claude failed: worker disconnected"

    run(tmp_path, scenario)


def test_frames_for_unknown_turns_or_other_workers_are_ignored(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, _bus, store = build(env)
        transport = connect(registry, worker)

        await coordinator.on_worker_frame(worker.id, TurnDone(turn_id="nope", text="x"))
        await coordinator.post_user_message(1, group.id, "@claude hi")
        await settle(lambda: transport.sent)
        await coordinator.on_worker_frame(worker.id + 1, TurnDone(turn_id=transport.sent[0]["turn_id"], text="x"))

        assert coordinator.is_running(group.id)  # still waiting for the right worker
        await coordinator.shutdown()

    run(tmp_path, scenario)


def test_the_next_turn_sends_only_what_the_worker_missed(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, _bus, _store = build(env)
        transport = connect(registry, worker)

        await coordinator.post_user_message(1, group.id, "@claude first")
        await settle(lambda: len(transport.sent) == 1)
        await coordinator.on_worker_frame(worker.id, TurnDone(turn_id=transport.sent[0]["turn_id"], text="one"))
        await settle(lambda: not coordinator.is_running(group.id))
        await coordinator.post_user_message(1, group.id, "@claude second")
        await settle(lambda: len(transport.sent) == 2)

        second = transport.sent[1]
        assert second["prompt"] == "@claude second" and second["history"] == []  # it saw 1 and 2 already
        await coordinator.shutdown()

    run(tmp_path, scenario)


def test_a_worker_added_late_gets_the_earlier_conversation(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        await env.allow("codex", "max")
        claude = await env.add_worker(label="claude")
        codex = await env.add_worker(provider="codex", label="codex")
        group = await env.add_group(workers=[claude, codex])
        coordinator, registry, _bus, _store = build(env)
        claude_wire, codex_wire = connect(registry, claude), connect(registry, codex)

        await coordinator.post_user_message(1, group.id, "@claude plan it")
        await settle(lambda: claude_wire.sent)
        await coordinator.on_worker_frame(claude.id, TurnDone(turn_id=claude_wire.sent[0]["turn_id"], text="Plan: A then B"))
        await settle(lambda: not coordinator.is_running(group.id))
        await coordinator.post_user_message(1, group.id, "@codex review it")
        await settle(lambda: codex_wire.sent)

        assert codex_wire.sent[0]["history"] == [
            {"sender": "user", "text": "@claude plan it"},
            {"sender": "claude", "text": "Plan: A then B"},
        ]
        await coordinator.shutdown()

    run(tmp_path, scenario)


def test_relay_hands_the_turn_on_up_to_the_depth_cap(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        await env.allow("codex", "max")
        claude = await env.add_worker(label="claude")
        codex = await env.add_worker(provider="codex", label="codex")
        group = await env.add_group(workers=[claude, codex], relay=True)
        coordinator, registry, _bus, store = build(env)
        wires = {claude.id: connect(registry, claude), codex.id: connect(registry, codex)}

        async def answer(worker, reply):
            await settle(lambda: wires[worker.id].sent and not wires[worker.id].sent[-1].get("_answered"))
            frame = wires[worker.id].sent[-1]
            frame["_answered"] = True
            await coordinator.on_worker_frame(worker.id, TurnDone(turn_id=frame["turn_id"], text=reply))

        await coordinator.post_user_message(1, group.id, "@claude start")
        await answer(claude, "wrote it\n@codex please review")
        await answer(codex, "looks fine\n@claude thanks, ship it")
        await answer(claude, "shipping\n@codex last look")
        await answer(codex, "ok\n@claude and again")  # a fourth hand-off: over the cap of 3
        await settle(lambda: not coordinator.is_running(group.id))

        assert wires[codex.id].sent[0]["prompt"] == "please review"
        assert wires[claude.id].sent[1]["prompt"] == "thanks, ship it"
        assert len(wires[claude.id].sent) == 2 and len(wires[codex.id].sent) == 2
        assert (await store.list_after(group.id))[-1].body["text"] == "ok\n@claude and again"

    run(tmp_path, scenario)


def test_without_relay_a_mention_in_a_reply_is_just_text(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        await env.allow("codex", "max")
        claude = await env.add_worker(label="claude")
        codex = await env.add_worker(provider="codex", label="codex")
        group = await env.add_group(workers=[claude, codex], relay=False)
        coordinator, registry, _bus, _store = build(env)
        claude_wire, codex_wire = connect(registry, claude), connect(registry, codex)

        await coordinator.post_user_message(1, group.id, "@claude start")
        await settle(lambda: claude_wire.sent)
        await coordinator.on_worker_frame(claude.id, TurnDone(turn_id=claude_wire.sent[0]["turn_id"], text="done\n@codex review"))
        await settle(lambda: not coordinator.is_running(group.id))

        assert codex_wire.sent == []

    run(tmp_path, scenario)


def test_a_permission_request_is_stored_answered_and_forwarded(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, _bus, store = build(env)
        transport = connect(registry, worker)

        await coordinator.post_user_message(1, group.id, "@claude go")
        await settle(lambda: transport.sent)
        turn_id = transport.sent[0]["turn_id"]
        await coordinator.on_worker_frame(
            worker.id, PermissionRequested(turn_id=turn_id, request_id="r1", tool="Bash", summary="npm test")
        )

        request = (await store.list_after(group.id))[-1]
        assert (request.kind, request.body["request_id"], request.body["tool"]) == ("permission_request", "r1", "Bash")

        assert await coordinator.resolve_permission(1, group.id, "r1", True) is True
        assert transport.sent[-1] == {"type": "permission_reply", "request_id": "r1", "allow": True}
        result = (await store.list_after(group.id))[-1]
        assert (result.kind, result.sender, result.body) == ("permission_result", "user", {"request_id": "r1", "allow": True, "by": "user"})
        assert await coordinator.resolve_permission(1, group.id, "r1", True) is False  # only once
        await coordinator.shutdown()

    run(tmp_path, scenario)


def test_only_the_owner_can_answer_a_permission(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, _bus, _store = build(env)
        transport = connect(registry, worker)
        await coordinator.post_user_message(1, group.id, "@claude go")
        await settle(lambda: transport.sent)
        await coordinator.on_worker_frame(
            worker.id, PermissionRequested(turn_id=transport.sent[0]["turn_id"], request_id="r1", tool="Bash")
        )

        with pytest.raises(GroupNotFound):
            await coordinator.resolve_permission(2, group.id, "r1", True)
        await coordinator.shutdown()

    run(tmp_path, scenario)


def test_an_unanswered_permission_is_denied_after_the_timeout(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, _bus, store = build(env, permission_timeout=0.05)
        transport = connect(registry, worker)
        await coordinator.post_user_message(1, group.id, "@claude go")
        await settle(lambda: transport.sent)
        await coordinator.on_worker_frame(
            worker.id, PermissionRequested(turn_id=transport.sent[0]["turn_id"], request_id="r1", tool="Bash")
        )

        await settle(lambda: transport.sent[-1].get("type") == "permission_reply")
        assert transport.sent[-1] == {"type": "permission_reply", "request_id": "r1", "allow": False}
        await settle_async(lambda: _last_kind(store, group, "permission_result"))
        result = (await store.list_after(group.id))[-1]
        assert (result.sender, result.body["by"]) == ("system", "timeout")
        await coordinator.shutdown()

    run(tmp_path, scenario)


def test_cancel_tells_the_worker_and_stops_the_turn_after_the_grace_time(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, _bus, store = build(env, cancel_grace=0.05)
        transport = connect(registry, worker)
        await coordinator.post_user_message(1, group.id, "@claude go")
        await settle(lambda: transport.sent)
        turn_id = transport.sent[0]["turn_id"]

        assert await coordinator.cancel(1, group.id) is True
        assert transport.sent[-1] == {"type": "cancel", "turn_id": turn_id}
        await settle(lambda: not coordinator.is_running(group.id))  # the worker never answered

        assert (await store.list_after(group.id))[-1].body["text"] == "@claude stopped."

    run(tmp_path, scenario)


def test_a_worker_that_acknowledges_the_cancel_ends_the_turn_at_once(tmp_path: Path) -> None:
    async def scenario(env):
        await env.allow("claude", "max")
        worker = await env.add_worker(label="claude")
        group = await env.add_group(workers=[worker])
        coordinator, registry, _bus, store = build(env, cancel_grace=30)
        transport = connect(registry, worker)
        await coordinator.post_user_message(1, group.id, "@claude go")
        await settle(lambda: transport.sent)
        turn_id = transport.sent[0]["turn_id"]

        await coordinator.cancel(1, group.id)
        await coordinator.on_worker_frame(worker.id, TurnError(turn_id=turn_id, message="cancelled"))
        await settle(lambda: not coordinator.is_running(group.id))

        assert (await store.list_after(group.id))[-1].body["text"] == "@claude stopped."

    run(tmp_path, scenario)


def test_cancel_with_nothing_running_is_a_no_op(tmp_path: Path) -> None:
    async def scenario(env):
        group = await env.add_group()
        coordinator, _registry, _bus, _store = build(env)

        assert await coordinator.cancel(1, group.id) is False
        with pytest.raises(GroupNotFound):
            await coordinator.cancel(2, group.id)

    run(tmp_path, scenario)
