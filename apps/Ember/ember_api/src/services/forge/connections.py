"""Live worker sockets. A connection wraps anything that can send text and close, so the
services never touch FastAPI's WebSocket type and tests use a fake."""

from __future__ import annotations

import asyncio
import json
from typing import Protocol


class Transport(Protocol):
    async def send_text(self, data: str) -> None: ...

    async def close(self, code: int = 1000) -> None: ...


class WorkerConnection:
    """One live worker socket. Sends are serialized so frames never interleave."""

    def __init__(self, worker_id: int, transport: Transport) -> None:
        self.worker_id = worker_id
        self._transport = transport
        self._lock = asyncio.Lock()

    async def send(self, frame: dict) -> None:
        async with self._lock:
            await self._transport.send_text(json.dumps(frame, ensure_ascii=False))

    async def close(self, code: int = 1000) -> None:
        try:
            await self._transport.close(code)
        except Exception:  # already closed or broken: nothing left to do
            pass


class WorkerRegistry:
    """Which workers are online right now: worker id to its newest connection."""

    def __init__(self) -> None:
        self._connections: dict[int, WorkerConnection] = {}

    def register(self, connection: WorkerConnection) -> WorkerConnection | None:
        """Returns the connection this one replaced (the caller closes it), if any."""
        replaced = self._connections.get(connection.worker_id)
        self._connections[connection.worker_id] = connection
        return replaced

    def get(self, worker_id: int) -> WorkerConnection | None:
        return self._connections.get(worker_id)

    def drop(self, worker_id: int, connection: WorkerConnection) -> None:
        """Forgets `connection`, unless a newer one has taken its place."""
        if self._connections.get(worker_id) is connection:
            del self._connections[worker_id]

    def is_online(self, worker_id: int) -> bool:
        return worker_id in self._connections
