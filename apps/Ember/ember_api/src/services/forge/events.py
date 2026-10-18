"""Live events for the browser: an in-memory fan-out per group, and the streamer that joins
the stored transcript to it. Single process, like the rest of Forge."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable

from src.services.forge.messages import MessageStore, message_event

QUEUE_MAX = 500


class Subscription:
    """One browser's queue of live events. If it falls too far behind it is told so
    (`lagged`) and ends; the browser reconnects and replays from its last `seq`."""

    def __init__(self, bus: GroupEventBus, group_id: int) -> None:
        self._bus = bus
        self.group_id = group_id
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._lagged = False

    def push(self, event: dict) -> None:
        if self._lagged:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._lagged = True

    async def events(self, ping_seconds: float = 20.0) -> AsyncIterator[dict]:
        while True:
            if self._lagged and self._queue.empty():
                yield {"type": "lagged"}
                return
            try:
                event = await asyncio.wait_for(self._queue.get(), ping_seconds)
            except asyncio.TimeoutError:
                yield {"type": "ping"}
                continue
            yield event

    def close(self) -> None:
        self._bus._remove(self)


class GroupEventBus:
    def __init__(self) -> None:
        self._subscriptions: dict[int, set[Subscription]] = {}

    def subscribe(self, group_id: int) -> Subscription:
        subscription = Subscription(self, group_id)
        self._subscriptions.setdefault(group_id, set()).add(subscription)
        return subscription

    def publish(self, group_id: int, event: dict) -> None:
        for subscription in tuple(self._subscriptions.get(group_id, ())):
            subscription.push(event)

    def _remove(self, subscription: Subscription) -> None:
        group = self._subscriptions.get(subscription.group_id)
        if group is not None:
            group.discard(subscription)
            if not group:
                del self._subscriptions[subscription.group_id]


def sse_frame(event: dict) -> bytes:
    """One server-sent-events frame. Stored messages carry `id: <seq>` so a browser can resume."""
    if event["type"] == "ping":
        return b": ping\n\n"
    prefix = f"id: {event['seq']}\n" if event["type"] == "message" else ""
    return f"{prefix}data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()


class GroupStreamer:
    """What one browser sees: stored messages after `after`, the turn state, then live events."""

    def __init__(self, bus: GroupEventBus, store: MessageStore, is_running: Callable[[int], bool]) -> None:
        self._bus = bus
        self._store = store
        self._is_running = is_running

    async def stream(self, group_id: int, after: int, ping_seconds: float = 20.0) -> AsyncIterator[dict]:
        # Subscribe first, so a message stored while we replay is not missed (it is deduplicated by seq).
        subscription = self._bus.subscribe(group_id)
        try:
            last = after
            for message in await self._store.list_after(group_id, after):
                last = message.seq
                yield message_event(message)
            yield {"type": "turn", "running": self._is_running(group_id)}
            async for event in subscription.events(ping_seconds):
                if event["type"] == "message":
                    if event["seq"] <= last:
                        continue
                    last = event["seq"]
                yield event
                if event["type"] == "lagged":
                    return
        finally:
            subscription.close()
