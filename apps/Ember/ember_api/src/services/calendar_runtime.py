"""Builds the calendar's moving parts once per app and hands them to the routes and the scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy import select

from src.config import Settings
from src.db import Database
from src.models import Account
from src.services.alert_channels import EmailChannel, InAppChannel, PushChannel, Recipient
from src.services.alert_scheduler import AlertScheduler
from src.services.calendar_events import EventSource, FeedCache
from src.services.calendar_fetcher import CalendarFetcher
from src.services.db_gateway import DocumentStore
from src.services.email_service import EmailSender
from src.services.log_service import LogWriter
from src.services.permissions import CALENDAR_USE
from src.services.secret_box import SecretBox
from src.services.settings_service import SettingsService
from src.services.vapid import ensure_vapid_keys


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
    *, settings: Settings, database: Database, store: DocumentStore, box: SecretBox,
    email_sender: EmailSender, log_writer: LogWriter,
) -> CalendarRuntime:
    config = settings.calendar
    client = httpx.AsyncClient(timeout=httpx.Timeout(config.fetch_timeout_s), follow_redirects=False)
    fetcher = CalendarFetcher(client, max_bytes=config.max_ics_bytes, allow_private_urls=config.allow_private_urls)
    events = EventSource(FeedCache(fetcher, timedelta(minutes=config.feed_refresh_minutes)))
    keys = ensure_vapid_keys(settings.env_path)

    async def lookup(uid: str) -> Recipient | None:
        async with database.sessions() as session:
            account = await session.scalar(select(Account).where(Account.uid == uid))
        if account is None or not account.is_active:
            return None
        if settings.require_email_verification and not account.email_verified:
            return None
        if CALENDAR_USE not in account.permission_names:
            return None
        return Recipient(account.uid, account.email)

    async def switches() -> dict[str, bool]:
        async with database.sessions() as session:
            return await SettingsService(session).all()

    scheduler = AlertScheduler(
        store=store, box=box, events=events, settings=config, lookup=lookup, switches=switches,
        channels={
            "inapp": InAppChannel(),
            "email": EmailChannel(email_sender),
            "push": PushChannel(keys.private, config.push_contact),
        },
        on_error=lambda message: log_writer.error(None, "calendar", message),
    )
    scheduler.start()
    return CalendarRuntime(events, scheduler, keys.public, client)
