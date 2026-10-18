from __future__ import annotations

import asyncio
from pathlib import Path

from src.services.forge.events import GroupEventBus, GroupStreamer, sse_frame
from src.services.forge.messages import MessageStore, message_event
from tests.forge_support import run


def test_append_numbers_messages_per_group_even_when_concurrent(tmp_path: Path) -> None:
    async def scenario(env):
        first, second = await env.add_group(), await env.add_group()
        store = MessageStore(env.database)
        sent = await asyncio.gather(*(store.append(first.id, "user", "text", {"text": str(n)}) for n in range(10)))
        other = await store.append(second.id, "user", "text", {"text": "x"})
        assert sorted(m.seq for m in sent) == list(range(1, 11))
        assert other.seq == 1
        assert await store.last_seq(first.id) == 10
        assert await store.last_seq(second.id) == 1

    run(tmp_path, scenario)


def test_list_after_returns_newer_messages_in_order(tmp_path: Path) -> None:
    async def scenario(env):
        group = await env.add_group()
        store = MessageStore(env.database)
        for n in range(5):
            await store.append(group.id, "user", "text", {"text": str(n)})
        assert [m.seq for m in await store.list_after(group.id, after=2)] == [3, 4, 5]
        assert [m.seq for m in await store.list_after(group.id, after=0, limit=2)] == [1, 2]

    run(tmp_path, scenario)


def test_history_is_text_only_after_the_cursor_and_skips_the_prompt(tmp_path: Path) -> None:
    async def scenario(env):
        group = await env.add_group()
        store = MessageStore(env.database)
        await store.append(group.id, "user", "text", {"text": "one"})  # 1
        await store.append(group.id, "1", "tool", {"name": "Edit"})  # 2: not text
        await store.append(group.id, "1", "text", {"text": "two", "label": "claude"})  # 3
        await store.append(group.id, "user", "text", {"text": "three"})  # 4: the prompt
        assert [m.seq for m in await store.history(group.id, 0, exclude_seq=4)] == [1, 3]
        assert [m.seq for m in await store.history(group.id, 1, exclude_seq=4)] == [3]
        assert [m.seq for m in await store.history(group.id, 0, limit=2)] == [3, 4]  # the newest two

    run(tmp_path, scenario)


def test_message_event_shape(tmp_path: Path) -> None:
    async def scenario(env):
        group = await env.add_group()
        message = await MessageStore(env.database).append(group.id, "user", "text", {"text": "hi"})
        event = message_event(message)
        assert event["type"] == "message" and event["seq"] == 1
        assert (event["sender"], event["kind"], event["body"]) == ("user", "text", {"text": "hi"})
        assert event["created_at"] == message.created_at.isoformat()

    run(tmp_path, scenario)


def test_the_bus_delivers_to_subscribers_of_that_group_only() -> None:
    async def go():
        bus = GroupEventBus()
        mine, other = bus.subscribe(1), bus.subscribe(2)
        bus.publish(1, {"type": "turn", "running": True})
        events = mine.events(ping_seconds=0.05)
        got = [await anext(events)]
        silent = await anext(other.events(ping_seconds=0.05))
        mine.close()
        other.close()
        return got, silent

    got, silent = asyncio.run(go())
    assert got == [{"type": "turn", "running": True}]
    assert silent == {"type": "ping"}


def test_a_closed_subscription_receives_nothing_more() -> None:
    bus = GroupEventBus()
    subscription = bus.subscribe(1)
    subscription.close()
    bus.publish(1, {"type": "turn", "running": True})

    assert subscription._queue.empty()


def test_a_slow_subscriber_is_told_it_lagged_and_ends() -> None:
    async def go():
        bus = GroupEventBus()
        subscription = bus.subscribe(1)
        for n in range(600):  # more than the queue holds
            bus.publish(1, {"type": "delta", "text": str(n)})
        return [event["type"] async for event in subscription.events(ping_seconds=0.05)]

    seen = asyncio.run(go())
    assert seen[-1] == "lagged" and seen.count("delta") == 500


def test_sse_frames() -> None:
    assert sse_frame({"type": "ping"}) == b": ping\n\n"
    assert sse_frame({"type": "message", "seq": 7, "body": {"text": "ü"}}) == (
        'id: 7\ndata: {"type": "message", "seq": 7, "body": {"text": "ü"}}\n\n'.encode()
    )
    assert sse_frame({"type": "turn", "running": True}) == b'data: {"type": "turn", "running": true}\n\n'


def test_the_streamer_replays_stored_messages_then_goes_live_without_repeats(tmp_path: Path) -> None:
    async def scenario(env):
        group = await env.add_group()
        bus, store = GroupEventBus(), MessageStore(env.database)
        running = {"value": True}
        streamer = GroupStreamer(bus, store, lambda _gid: running["value"])
        for n in range(3):
            await store.append(group.id, "user", "text", {"text": str(n)})
        stream = streamer.stream(group.id, after=1, ping_seconds=0.05)

        replay = [await anext(stream), await anext(stream)]
        state = await anext(stream)
        assert [e["seq"] for e in replay] == [2, 3]
        assert state == {"type": "turn", "running": True}

        live = await store.append(group.id, "user", "text", {"text": "live"})
        bus.publish(group.id, message_event(live))
        bus.publish(group.id, message_event(live))  # a duplicate must not be repeated
        bus.publish(group.id, {"type": "delta", "turn_id": "t", "sender": "1", "text": "x"})
        assert (await anext(stream))["seq"] == 4
        assert (await anext(stream))["type"] == "delta"
        assert (await anext(stream))["type"] == "ping"
        await stream.aclose()

    run(tmp_path, scenario)
