"""Turn and unit time limits that stop counting while the user answers a server's question."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from typing import Any


class Deadline:
    """One asyncio.timeout that can be paused. Use it only on its own event loop."""

    def __init__(self, timeout: asyncio.Timeout) -> None:
        self._timeout = timeout
        self._holds = 0
        self._remaining: float | None = None

    def hold(self) -> None:
        self._holds += 1
        if self._holds > 1:
            return
        when = self._timeout.when()
        if when is not None:
            self._remaining = max(0.0, when - asyncio.get_running_loop().time())
            self._move(None)

    def release(self) -> None:
        if self._holds == 0:
            return
        self._holds -= 1
        if self._holds == 0 and self._remaining is not None:
            self._move(asyncio.get_running_loop().time() + self._remaining)
            self._remaining = None

    def _move(self, when: float | None) -> None:
        with suppress(RuntimeError):  # already expired, or already left
            self._timeout.reschedule(when)


_active: ContextVar[tuple[Deadline, ...]] = ContextVar("deadlines", default=())


@asynccontextmanager
async def deadline(seconds: float) -> AsyncIterator[Deadline]:
    """asyncio.timeout(seconds) that UserWaits can pause."""
    async with asyncio.timeout(seconds) as timeout:
        entry = Deadline(timeout)
        token = _active.set((*_active.get(), entry))
        try:
            yield entry
        finally:
            _active.reset(token)


class UserWaits:
    """Pauses the limits active now while any question seen by one tool step is open."""

    def __init__(self) -> None:
        self._deadlines = _active.get()
        self._open: set[str] = set()

    def note(self, event: dict[str, Any]) -> None:
        kind, key = event.get("type"), str(event.get("id") or "")
        if kind == "elicitation_request" and key not in self._open:
            self._open.add(key)
            for entry in self._deadlines:
                entry.hold()
        elif kind == "elicitation_resolved" and key in self._open:
            self._open.remove(key)
            for entry in self._deadlines:
                entry.release()

    def close(self) -> None:
        for key in list(self._open):
            self.note({"type": "elicitation_resolved", "id": key})
