"""Asks a worker to open a folder dialog on its own computer and waits for the user's pick.

The browser cannot see the worker's disk, so the worker does the browsing: Ember sends a
`browse` frame and the worker answers with a `browse_result` frame."""

from __future__ import annotations

import asyncio
import uuid

from src.services.forge.connections import WorkerRegistry
from src.services.forge.protocol import BrowseResult, browse_frame

DEFAULT_TIMEOUT_SECONDS = 180.0


class WorkerOffline(Exception):
    """The worker is not connected (or dropped while the dialog was open)."""


class BrowseInProgress(Exception):
    """That worker already has a folder dialog open."""


class BrowseTimeout(Exception):
    """Nobody chose a folder in time."""


class FolderBrowser:
    def __init__(self, registry: WorkerRegistry, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._registry = registry
        self._timeout = timeout_seconds
        # worker id to the request waiting on it; one dialog per worker at a time
        self._waiting: dict[int, tuple[str, asyncio.Future[str | None]]] = {}

    async def pick(self, worker_id: int, start: str | None = None) -> str | None:
        """The folder the user chose in the worker's dialog, or None when they cancelled."""
        connection = self._registry.get(worker_id)
        if connection is None:
            raise WorkerOffline(worker_id)
        if worker_id in self._waiting:
            raise BrowseInProgress(worker_id)
        request_id = uuid.uuid4().hex
        future: asyncio.Future[str | None] = asyncio.get_running_loop().create_future()
        self._waiting[worker_id] = (request_id, future)
        try:
            await connection.send(browse_frame(request_id, start))
            return await asyncio.wait_for(future, self._timeout)
        except asyncio.TimeoutError:
            raise BrowseTimeout(worker_id) from None
        finally:
            if self._waiting.get(worker_id, (None,))[0] == request_id:
                del self._waiting[worker_id]

    def on_result(self, worker_id: int, frame: BrowseResult) -> None:
        """A worker's answer. One that does not match the open request is ignored."""
        waiting = self._waiting.get(worker_id)
        if waiting is None or waiting[0] != frame.request_id or waiting[1].done():
            return
        waiting[1].set_result(frame.path)

    def on_disconnected(self, worker_id: int) -> None:
        waiting = self._waiting.get(worker_id)
        if waiting is not None and not waiting[1].done():
            waiting[1].set_exception(WorkerOffline(worker_id))

    def close(self) -> None:
        for worker_id in list(self._waiting):
            self.on_disconnected(worker_id)
