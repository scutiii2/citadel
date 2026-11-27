"""Chat holds across every file store: a held file lives until the last chat holding it is removed."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Any

from src.services.session_file_store import SessionFileStore

logger = logging.getLogger(__name__)

StoreAction = Callable[[SessionFileStore], Awaitable[Any]]


class HoldsUnavailable(Exception):
    """A store could not be reached; the caller retries (every call is safe to repeat)."""


@dataclass(frozen=True)
class HoldTarget:
    """One file store: how to run an action on its own loop, and how it names an account."""

    name: str
    run: Callable[[StoreAction], Any]  # blocking
    session: Callable[[str], str]


class ChatHolds:
    """Every method blocks; call it from a worker thread."""

    def __init__(self, targets: Collection[HoldTarget]) -> None:
        self._targets = tuple(targets)

    def hold(self, uid: str, chat_id: str, file_ids: Collection[str]) -> list[str]:
        results = self._each(uid, lambda store, session: store.hold(session, chat_id, file_ids))
        return sorted({file_id for held in results for file_id in held})

    def release(self, uid: str, chat_ids: Collection[str] | None) -> int:
        return sum(self._each(uid, lambda store, session: store.release(session, chat_ids)))

    def _each(self, uid: str, action: Callable[[SessionFileStore, str], Awaitable[Any]]) -> list[Any]:
        results, failed = [], []
        for target in self._targets:
            try:
                session = target.session(uid)
                results.append(target.run(lambda store: action(store, session)))
            except Exception:
                logger.exception("Chat holds: the %s store failed", target.name)
                failed.append(target.name)
        if failed:
            raise HoldsUnavailable(f"File storage is unavailable: {', '.join(failed)}")
        return results
