"""One background task that sends the queued chat file holds to Armory and retries until they are accepted."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from src.chats.armory_holds import ArmoryHolds, HoldNotAccepted, HoldRefused, HoldsUnreachable
from src.chats.file_holds import HOLD, RELEASE_ALL, ChatFileHolds

logger = logging.getLogger(__name__)

_GROUP = 500  # ids per call, Armory's limit
_MAX_RETRY = 300.0


class HoldSender:
    def __init__(self, queue: ChatFileHolds, armory: ArmoryHolds,
                 chat_exists: Callable[[str, str], Awaitable[bool]], *,
                 idle: float = 300.0, first_retry: float = 5.0) -> None:
        self._queue = queue
        self._armory = armory
        self._chat_exists = chat_exists
        self._idle = idle
        self._first_retry = first_retry

    async def send_pending(self) -> bool:
        """One pass over the queue; False when something has to be tried again."""
        complete = True
        for doc in await self._queue.pending():
            try:
                await self._send(doc)
            except HoldsUnreachable:
                return False
            except HoldNotAccepted as error:
                logger.warning("Chat file hold %s waits: %s", doc["key"], error)
                complete = False
                continue
            except HoldRefused as error:
                logger.error("Chat file hold %s dropped: %s", doc["key"], error)
            await self._queue.done(doc)
        return complete

    async def run(self) -> None:
        """Until cancelled: send, then sleep until a new call is queued; after a failure wait longer each time."""
        delay = self._first_retry
        while True:
            self._queue.added.clear()
            try:
                complete = await self.send_pending()
            except Exception:
                logger.exception("Sending chat file holds failed")
                complete = False
            if complete:
                delay = self._first_retry
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._queue.added.wait(), self._idle)
            else:
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RETRY)

    async def _send(self, doc: dict[str, Any]) -> None:
        """Sends one call; one that no longer applies sends nothing."""
        owner, chat_id = doc["owner"], doc["chat_id"]
        if doc["op"] == RELEASE_ALL:
            await self._armory.release_all(owner)
        elif doc["op"] == HOLD:
            if await self._chat_exists(owner, chat_id):
                ids = doc["file_ids"]
                for start in range(0, len(ids), _GROUP):
                    await self._armory.hold(owner, chat_id, ids[start:start + _GROUP])
        elif not await self._chat_exists(owner, chat_id):
            await self._armory.release(owner, [chat_id])
