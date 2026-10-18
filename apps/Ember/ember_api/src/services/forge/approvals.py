"""Tool-permission requests waiting for the user's Allow or Deny. An unanswered request is
reported to `on_timeout` (the coordinator denies it) after `timeout_seconds`."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class PendingPermission:
    request_id: str
    group_id: int
    worker_id: int
    turn_id: str


class PermissionBroker:
    def __init__(
        self, on_timeout: Callable[[PendingPermission], Awaitable[None]], timeout_seconds: float = 600.0
    ) -> None:
        self._on_timeout = on_timeout
        self._timeout = timeout_seconds
        self._pending: dict[str, PendingPermission] = {}
        self._timers: dict[str, asyncio.Task] = {}

    def open(self, pending: PendingPermission) -> None:
        self._pending[pending.request_id] = pending
        self._timers[pending.request_id] = asyncio.create_task(self._expire(pending))

    def resolve(self, group_id: int, request_id: str) -> PendingPermission | None:
        """Takes the request out of the queue; None when it is unknown, answered, or another group's."""
        pending = self._pending.get(request_id)
        if pending is None or pending.group_id != group_id:
            return None
        self._forget(request_id)
        return pending

    def discard_turn(self, turn_id: str) -> list[PendingPermission]:
        dropped = [p for p in self._pending.values() if p.turn_id == turn_id]
        for pending in dropped:
            self._forget(pending.request_id)
        return dropped

    def close(self) -> None:
        for request_id in list(self._pending):
            self._forget(request_id)

    def _forget(self, request_id: str) -> None:
        self._pending.pop(request_id, None)
        timer = self._timers.pop(request_id, None)
        if timer is not None and timer is not asyncio.current_task():
            timer.cancel()

    async def _expire(self, pending: PendingPermission) -> None:
        await asyncio.sleep(self._timeout)
        if self._pending.get(pending.request_id) is None:
            return
        self._forget(pending.request_id)
        await self._on_timeout(pending)
