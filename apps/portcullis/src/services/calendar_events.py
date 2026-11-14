"""Feed bodies kept in memory for a few minutes, and the events they hold."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.services.calendar_expander import CalendarEvent, expand, merge
from src.services.calendar_fetcher import FeedError, FetchResult
from src.services.calendar_store import CalendarError, CalendarStore, Feed


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _Entry:
    body: bytes
    etag: str | None
    at: datetime


@dataclass(frozen=True)
class EventResult:
    events: list[CalendarEvent]
    errors: list[tuple[str, str]]  # (feed name, message)


class FeedCache:
    """shortcut: bodies live in memory (at most max_ics_bytes per feed) and are lost on restart; persist them if cold starts hurt."""

    def __init__(self, fetcher, refresh: timedelta, clock: Callable[[], datetime] = utc_now) -> None:
        self._fetcher = fetcher
        self._refresh = refresh
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def forget(self, owner: str, feed_id: str) -> None:
        self._entries.pop(f"{owner}:{feed_id}", None)

    async def body(self, cal: CalendarStore, feed: Feed) -> bytes:
        key = cal.feed_key(feed)
        async with self._locks.setdefault(key, asyncio.Lock()):
            entry = self._entries.get(key)
            now = self._clock()
            if entry is not None and now - entry.at < self._refresh:
                return entry.body
            try:
                result: FetchResult = await self._fetcher.fetch(cal.feed_url(feed), entry.etag if entry else None)
            except FeedError as error:
                await cal.record_fetch(feed.id, error=str(error))
                if entry is not None:
                    return entry.body  # keep showing the last good copy
                raise
            body = entry.body if result.not_modified and entry is not None else result.body
            assert body is not None
            self._entries[key] = _Entry(body, result.etag or (entry.etag if entry else None), now)
            await cal.record_fetch(feed.id, error=None)
            return body


class EventSource:
    def __init__(self, cache: FeedCache) -> None:
        self._cache = cache

    def forget(self, owner: str, feed_id: str) -> None:
        self._cache.forget(owner, feed_id)

    async def events(self, cal: CalendarStore, start: datetime, end: datetime) -> EventResult:
        zone = await cal.zone()
        feeds = [f for f in await cal.feeds() if f.enabled]

        async def one(feed: Feed) -> tuple[list[CalendarEvent], tuple[str, str] | None]:
            try:
                body = await self._cache.body(cal, feed)
            except (FeedError, CalendarError) as error:
                return [], (feed.name, str(error))
            try:
                return await asyncio.to_thread(expand, body, start, end, zone, feed.name), None
            except Exception:  # a hostile or broken file can fail in many ways; none is worth more than a message
                return [], (feed.name, "The feed is not a valid calendar")

        results = await asyncio.gather(*(one(feed) for feed in feeds))
        return EventResult(merge([events for events, _ in results]), [error for _, error in results if error])
