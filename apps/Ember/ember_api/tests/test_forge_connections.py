from __future__ import annotations

import asyncio

from src.services.forge.connections import WorkerConnection, WorkerRegistry
from tests.forge_support import FakeTransport


def test_send_serializes_the_frame_as_json() -> None:
    async def go():
        transport = FakeTransport()
        await WorkerConnection(1, transport).send({"type": "ready", "worker_id": 1, "note": "ü"})
        return transport.sent

    assert asyncio.run(go()) == [{"type": "ready", "worker_id": 1, "note": "ü"}]


def test_concurrent_sends_do_not_interleave() -> None:
    class SlowTransport(FakeTransport):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.overlaps = 0

        async def send_text(self, data: str) -> None:
            self.active += 1
            self.overlaps += self.active > 1
            await asyncio.sleep(0.01)
            self.active -= 1
            await super().send_text(data)

    async def go():
        transport = SlowTransport()
        connection = WorkerConnection(1, transport)
        await asyncio.gather(*(connection.send({"n": n}) for n in range(5)))
        return transport.overlaps, len(transport.sent)

    assert asyncio.run(go()) == (0, 5)


def test_close_never_raises() -> None:
    class Broken(FakeTransport):
        async def close(self, code: int = 1000) -> None:
            raise RuntimeError("already closed")

    asyncio.run(WorkerConnection(1, Broken()).close(4401))


def test_registering_a_second_connection_returns_the_first() -> None:
    registry = WorkerRegistry()
    first, second = WorkerConnection(7, FakeTransport()), WorkerConnection(7, FakeTransport())

    assert registry.register(first) is None
    assert registry.register(second) is first
    assert registry.get(7) is second and registry.is_online(7)


def test_drop_only_removes_the_connection_that_is_still_registered() -> None:
    registry = WorkerRegistry()
    first, second = WorkerConnection(7, FakeTransport()), WorkerConnection(7, FakeTransport())
    registry.register(first)
    registry.register(second)

    registry.drop(7, first)  # a late cleanup of the replaced connection
    assert registry.get(7) is second

    registry.drop(7, second)
    assert registry.get(7) is None and not registry.is_online(7)
