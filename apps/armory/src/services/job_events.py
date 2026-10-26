"""A background job's replayable event log, shared by the pdf_merger and media_downloader queues.
publish() runs on the event loop thread; worker threads hop to it with call_soon_threadsafe."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    session: str
    created_at: float
    events: list[dict] = field(default_factory=list)
    finished: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    _changed: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def cancel(self) -> None:
        """Ask the job to stop: a queued job never starts, a running one stops cooperatively."""
        self.cancel_event.set()

    def publish(self, event: dict, *, final: bool = False) -> None:
        """Append an event. Events after the final one are dropped."""
        if self.finished:
            return
        self.events.append(event)
        self.finished = final
        self._changed.set()

    async def stream(self) -> AsyncIterator[dict]:
        """Every event so far, then new ones as they arrive, ending after the final event."""
        index = 0
        while True:
            while index < len(self.events):
                yield self.events[index]
                index += 1
            if self.finished:
                return
            self._changed.clear()
            await self._changed.wait()
