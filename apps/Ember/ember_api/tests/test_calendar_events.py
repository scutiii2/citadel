from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from src.config import CalendarSettings
from src.services.calendar_events import EventSource, FeedCache
from src.services.calendar_fetcher import FeedError, FetchResult
from src.services.calendar_store import CalendarStore
from src.services.secret_box import SecretBox
from tests.conftest import FakeDbGateway

ICS = (
    "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//t//EN\nBEGIN:VEVENT\nUID:e1\n"
    "DTSTART:20261026T090000Z\nDTEND:20261026T100000Z\nSUMMARY:Standup\nEND:VEVENT\nEND:VCALENDAR\n"
).encode()
START, END = datetime(2026, 10, 26, tzinfo=timezone.utc), datetime(2026, 10, 27, tzinfo=timezone.utc)


class FakeFetcher:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, str | None]] = []

    async def fetch(self, url: str, etag: str | None = None) -> FetchResult:
        self.calls.append((url, etag))
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 26, 8, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


def setup(fetcher: FakeFetcher, clock: Clock):
    cal = CalendarStore(FakeDbGateway(), "u1", SecretBox(Fernet.generate_key().decode("ascii")), CalendarSettings())
    feed = asyncio.run(cal.add_feed("Work", "https://x.com/a.ics", "#2563eb"))
    return cal, feed, EventSource(FeedCache(fetcher, timedelta(minutes=10), clock))


def test_events_come_from_the_feed_and_the_body_is_cached_for_the_refresh_period() -> None:
    fetcher, clock = FakeFetcher(FetchResult(ICS, '"1"')), Clock()
    cal, feed, source = setup(fetcher, clock)
    first = asyncio.run(source.events(cal, START, END))
    assert [(e.title, e.sources) for e in first.events] == [("Standup", ("Work",))] and first.errors == []
    asyncio.run(source.events(cal, START, END))
    assert len(fetcher.calls) == 1
    clock.now += timedelta(minutes=11)
    fetcher.results = [FetchResult(None, '"1"')]
    asyncio.run(source.events(cal, START, END))
    assert fetcher.calls[-1] == ("https://x.com/a.ics", '"1"')  # revalidated with the etag, body reused


def test_a_failing_feed_keeps_the_last_good_copy_and_records_the_error() -> None:
    fetcher, clock = FakeFetcher(FetchResult(ICS, None)), Clock()
    cal, feed, source = setup(fetcher, clock)
    asyncio.run(source.events(cal, START, END))
    clock.now += timedelta(minutes=11)
    fetcher.results = [FeedError("The feed answered HTTP 500")]
    got = asyncio.run(source.events(cal, START, END))
    assert len(got.events) == 1
    assert asyncio.run(cal.feed(feed.id)).last_error == "The feed answered HTTP 500"


def test_a_feed_that_never_worked_is_reported_not_raised() -> None:
    cal, feed, source = setup(FakeFetcher(FeedError("The feed could not be reached")), Clock())
    got = asyncio.run(source.events(cal, START, END))
    assert got.events == [] and got.errors == [("Work", "The feed could not be reached")]


def test_garbage_is_reported_as_an_invalid_calendar_and_disabled_feeds_are_skipped() -> None:
    cal, feed, source = setup(FakeFetcher(FetchResult(b"not a calendar", None)), Clock())
    got = asyncio.run(source.events(cal, START, END))
    assert got.errors == [("Work", "The feed is not a valid calendar")]
    asyncio.run(cal.update_feed(feed.id, enabled=False))
    assert asyncio.run(source.events(cal, START, END)).errors == []
