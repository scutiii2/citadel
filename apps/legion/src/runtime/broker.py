"""Shared wait/resolve core of the approval and question brokers.

A waiter parks a future under (request_id, step_id); a different MCP tool call resolves
it. `wait` polls so Stop (cancellation) and a deadline end it within `poll` seconds.
Both sides run on the server's event loop, so futures are set and awaited on one loop.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Generic, TypeVar

from src.providers import cancellation

T = TypeVar("T")


class Broker(Generic[T]):
    def __init__(self, timeout: float, poll: float) -> None:
        self._timeout = timeout
        self._poll = poll
        self._pending: dict[tuple[str, str], asyncio.Future[T]] = {}

    async def _wait(
        self,
        request_id: str,
        step_id: str,
        *,
        replaced: T,
        cancelled: T,
        timed_out: T,
        tick: Callable[[float], Awaitable[None]] | None = None,
    ) -> T:
        """The resolved value, or `cancelled` / `timed_out`. A second wait on the same step
        resolves the first with `replaced`. `tick(now)` runs before each poll."""
        loop = asyncio.get_running_loop()
        key = (request_id, step_id)
        previous = self._pending.get(key)
        if previous is not None and not previous.done():
            previous.set_result(replaced)
        future: asyncio.Future[T] = loop.create_future()
        self._pending[key] = future
        deadline = loop.time() + self._timeout
        try:
            while True:
                if cancellation.is_cancelled(request_id):
                    return cancelled
                now = loop.time()
                remaining = deadline - now
                if remaining <= 0:
                    return timed_out
                if tick is not None:
                    await tick(now)
                try:
                    return await asyncio.wait_for(asyncio.shield(future), min(self._poll, remaining))
                except asyncio.TimeoutError:
                    continue
        finally:
            if self._pending.get(key) is future:
                del self._pending[key]

    def _resolve(self, request_id: str, step_id: str, value: T) -> bool:
        """False when nothing waits for that request and step, or it was already resolved."""
        future = self._pending.get((request_id, step_id))
        if future is None or future.done():
            return False
        future.set_result(value)
        return True
