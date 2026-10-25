"""Live progress reporting for long tool calls: ``domain.py`` calls ``report("...")``; ``offload.offload_with_progress`` binds a sink forwarding it as ``notifications/progress``.
With no sink (tests, watcher threads, no progress token) it is a no-op. A ``ContextVar`` carries the sink across ``asyncio.to_thread``."""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Callable

logger = logging.getLogger(__name__)

Sink = Callable[[str], None]

_sink: ContextVar[Sink | None] = ContextVar("progress_sink", default=None)


def bind(sink: Sink) -> Token:
    return _sink.set(sink)


def reset(token: Token) -> None:
    _sink.reset(token)


def report(message: str) -> None:
    sink = _sink.get()
    if sink is None:
        return
    try:
        sink(message)
    except Exception:  # noqa: BLE001 - progress is best-effort, never fail the tool over it
        logger.debug("progress sink failed", exc_info=True)
