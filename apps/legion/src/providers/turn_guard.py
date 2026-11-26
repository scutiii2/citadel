"""Shared per-turn budgets and repeated-call detection for tool loops."""

from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager
from typing import Any

from src.citadel_auth.failure import parse
from src.providers import deadlines


class TurnStopped(Exception):
    """A guard ended the turn with an explanation safe to show the user."""


class TurnGuard:
    """Bound elapsed time, reported tokens, and identical calls within one turn.

    Usage is reported at round boundaries, so a token cap may overshoot by
    one response. Timeouts interrupt async waits; synchronous tools already
    running on a worker cannot be forcibly undone.
    """

    def __init__(self, max_tokens: int = 100_000, max_seconds: float = 300) -> None:
        self.max_tokens = max_tokens
        self.max_seconds = max_seconds
        self._last_call: str | None = None
        self._repetitions = 0
        self._failures: dict[str, str] = {}

    def timeout(self) -> AbstractAsyncContextManager[deadlines.Deadline]:
        """Apply the turn deadline to the entire provider loop. Waiting on a server's question does not count."""
        return deadlines.deadline(self.max_seconds)

    def check_tokens(self, total: int | None) -> None:
        if total is not None and total >= self.max_tokens:
            raise TurnStopped(f"Stopped: this turn reached its token budget ({self.max_tokens:,} tokens).")

    @staticmethod
    def _call_key(name: str, arguments: Any) -> str:
        return json.dumps([name, arguments], sort_keys=True, separators=(",", ":"))

    def note_result(self, name: str, arguments: Any, text: str) -> None:
        failure = parse(text)
        if failure is None:
            return
        key = self._call_key(name, arguments)
        if failure.retryable is False:
            self._failures[key] = failure.text
        elif key == self._last_call:
            self._last_call = None

    def check_call(self, name: str, arguments: Any) -> None:
        key = self._call_key(name, arguments)
        if key in self._failures:
            raise TurnStopped(self._failures[key])
        self._repetitions = self._repetitions + 1 if key == self._last_call else 1
        self._last_call = key
        if self._repetitions >= 3:
            raise TurnStopped(f"Stopped: tool '{name}' repeated the same arguments three times without progress.")

    def time_message(self) -> str:
        return f"Stopped: this turn reached its time budget ({self.max_seconds:g} seconds)."
