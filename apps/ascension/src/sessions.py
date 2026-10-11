"""Expiring in-memory game sessions with bounded capacity."""
from __future__ import annotations

import secrets
import time
from collections import OrderedDict
from collections.abc import Callable


class GameSessions:
    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic, max_sessions: int = 1000) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._max_sessions = max_sessions
        self._sessions: OrderedDict[str, tuple[str, float]] = OrderedDict()

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    def open(self, owner: str) -> str:
        now = self._clock()
        while self._sessions and next(iter(self._sessions.values()))[1] <= now:
            self._sessions.popitem(last=False)
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (owner, now + self._ttl_seconds)
        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)
        return token

    def owner_of(self, token: str) -> str | None:
        session = self._sessions.get(token)
        if session is None:
            return None
        owner, expires_at = session
        if expires_at <= self._clock():
            del self._sessions[token]
            return None
        return owner
