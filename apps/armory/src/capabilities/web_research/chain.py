"""Tries engines in order until one answers, within a time budget that fits Legion's tool call limit (120 s)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from src.capabilities.web_research.engines.base import Engine, EngineError, PageMissing
from src.citadel_auth.failure import Code, Failure

logger = logging.getLogger(__name__)

DEPENDENCY = "web"
ENGINE_SECONDS = 30.0
CRAWL_SECONDS = 60.0
START_BEFORE_SECONDS = 90.0  # no new engine starts after this
DEADLINE_SECONDS = 110.0  # and none gets time beyond this

T = TypeVar("T")


@dataclass(frozen=True)
class Outcome(Generic[T]):
    """What the chain ended with. `value` is None when every answer was empty or the page does not exist."""

    engine: str
    value: T | None
    missing_status: int | None = None


class EngineChain:
    def __init__(self, engines: Sequence[Engine], clock: Callable[[], float] = time.monotonic) -> None:
        self._engines = tuple(engines)
        self._clock = clock

    def run(self, operation: str, call: Callable[[Engine, float], T]) -> Outcome[T]:
        """`call(engine, seconds)` for each configured engine that supports `operation`. A falsy value counts as empty.
        Raises `Failure` when no engine is configured, or when none answered and at least one failed."""
        engines = [engine for engine in self._engines if operation in engine.operations and engine.configured()]
        if not engines:
            raise Failure(Code.DEP_NOT_CONFIGURED, DEPENDENCY)
        seconds = CRAWL_SECONDS if operation == "crawl" else ENGINE_SECONDS
        started = self._clock()
        failed: Code | None = None
        answered = ""
        for engine in engines:
            elapsed = self._clock() - started
            if elapsed >= START_BEFORE_SECONDS:
                break
            try:
                value = call(engine, min(seconds, DEADLINE_SECONDS - elapsed))
            except PageMissing as missing:
                return Outcome(engine.name, None, missing.status)
            except EngineError as error:
                logger.warning("web %s: %s", operation, error.reason)
                failed = failed or error.code
                continue
            except (AttributeError, KeyError, TypeError, ValueError):
                logger.exception("web %s: %s sent an unreadable reply", operation, engine.name)
                failed = failed or Code.DEP_ERROR
                continue
            if value:
                return Outcome(engine.name, value)
            logger.info("web %s: %s answered with nothing", operation, engine.name)
            answered = engine.name
        if not answered and failed:
            raise Failure(failed, DEPENDENCY)
        return Outcome(answered, None)
