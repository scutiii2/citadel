"""Builds the calendar's moving parts once per app and hands them to the routes and the scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import httpx

from src.calendar.channels import EmailChannel, InAppChannel, PushChannel, Recipient
from src.calendar.events import EventSource, FeedCache
from src.calendar.fetcher import CalendarFetcher
from src.calendar.scheduler import AlertScheduler
from src.calendar.settings import CalendarSettings
from src.document_store import DocumentStore
from src.keys import Keys
from src.platform import PortcullisClient
from src.secret_box import SecretBox

# The permission an account must still hold when an alert fires (checked by Portcullis).
PERMISSION = "calendar.use"


@dataclass
class CalendarRuntime:
    """Mutable on purpose: tests swap `events` for one with a fake fetcher."""

    events: EventSource
    scheduler: AlertScheduler | None
    vapid_public: str
    client: httpx.AsyncClient

    async def close(self) -> None:
        if self.scheduler is not None:
            await self.scheduler.stop()
        await self.client.aclose()


def build_calendar_runtime(
    *, config: CalendarSettings, store: DocumentStore, box: SecretBox, keys: Keys, platform: PortcullisClient,
) -> CalendarRuntime:
    client = httpx.AsyncClient(timeout=httpx.Timeout(config.fetch_timeout_s), follow_redirects=False)
    fetcher = CalendarFetcher(client, max_bytes=config.max_ics_bytes, allow_private_urls=config.allow_private_urls)
    events = EventSource(FeedCache(fetcher, timedelta(minutes=config.feed_refresh_minutes)))

    async def lookup(uid: str) -> Recipient | None:
        found = await platform.recipient(uid, PERMISSION)
        return None if found is None else Recipient(found["uid"], found["email"])

    scheduler = AlertScheduler(
        store=store, box=box, events=events, settings=config, lookup=lookup, switches=platform.switches,
        channels={
            "inapp": InAppChannel(),
            "email": EmailChannel(platform.notify),
            "push": PushChannel(keys.vapid_private, config.push_contact),
        },
        on_error=lambda message: platform.report_error("calendar", message),
    )
    scheduler.start()
    return CalendarRuntime(events, scheduler, keys.vapid_public, client)
