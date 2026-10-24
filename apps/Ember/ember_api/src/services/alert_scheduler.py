"""Fires alarm rules before events. Started in the app lifespan, like BackupScheduler."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timedelta

from src.config import CalendarSettings
from src.services.alert_channels import AlertMessage, Channel, Recipient
from src.services.calendar_events import EventSource, utc_now
from src.services.calendar_expander import CalendarEvent
from src.services.calendar_store import CalendarStore, Rule, StoredAlert, owners_with_rules
from src.services.db_gateway import DbGatewayError, DocumentStore
from src.services.secret_box import SecretBox

logger = logging.getLogger(__name__)


def is_due(start: datetime, lead_minutes: int, now: datetime, grace_minutes: int) -> bool:
    """True from `lead_minutes` before the event until `grace_minutes` later, and never after it began."""
    fire_at = start - timedelta(minutes=lead_minutes)
    return fire_at <= now <= fire_at + timedelta(minutes=grace_minutes) and now < start


class AlertScheduler:
    def __init__(
        self,
        *,
        store: DocumentStore,
        box: SecretBox,
        events: EventSource,
        channels: Mapping[str, Channel],
        settings: CalendarSettings,
        lookup: Callable[[str], Awaitable[Recipient | None]],
        switches: Callable[[], Awaitable[dict[str, bool]]],
        on_error: Callable[[str], Awaitable[None]] | None = None,
        clock: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._store, self._box, self._events, self._channels = store, box, events, channels
        self._settings, self._lookup, self._switches = settings, lookup, switches
        self._on_error, self._clock, self._sleep = on_error, clock, sleep
        self._upcoming: dict[str, tuple[datetime, list[CalendarEvent]]] = {}
        self._last_report = ""
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="calendar-alerts")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _loop(self) -> None:
        while True:
            await self._sleep(self._settings.tick_seconds)
            try:
                await self.tick(self._clock())
            except Exception as error:  # a bad tick must never end the loop
                logger.exception("calendar tick failed")
                await self._report(f"calendar alerts could not run: {type(error).__name__}")

    async def _report(self, message: str) -> None:
        """Tell the Errors log, but not the same thing again on every tick."""
        if self._on_error is not None and message != self._last_report:
            self._last_report = message
            await self._on_error(message)

    async def tick(self, now: datetime) -> None:
        switches = await self._switches()
        for owner in sorted(await owners_with_rules(self._store)):
            try:
                await self._tick_owner(owner, now, switches)
            except DbGatewayError:
                raise  # storage is down for everyone: the loop reports it once
            except Exception as error:
                logger.exception("calendar alerts failed for one account")
                await self._report(f"calendar alerts failed for an account: {type(error).__name__}")

    async def _tick_owner(self, owner: str, now: datetime, switches: dict[str, bool]) -> None:
        recipient = await self._lookup(owner)
        if recipient is None:
            return
        cal = CalendarStore(self._store, owner, self._box, self._settings)
        rules = [r for r in await cal.rules() if r.enabled and switches.get(f"calendar_{r.channel}", False)]
        if not rules:
            return
        refresh = timedelta(minutes=self._settings.feed_refresh_minutes)
        cached = self._upcoming.get(owner)
        if cached is None or now - cached[0] >= refresh:
            horizon = now + timedelta(hours=self._settings.lookahead_hours)
            cached = (now, (await self._events.events(cal, now, horizon)).events)
            self._upcoming[owner] = cached
            await cal.prune_alerts(now)
        for event in cached[1]:
            if event.all_day:
                continue
            for rule in rules:
                if is_due(event.start, rule.lead_minutes, now, self._settings.late_grace_minutes):
                    alert = await cal.create_alert(rule, event)
                    if alert is not None:
                        await self._dispatch(cal, recipient, rule, event, alert)

    async def _dispatch(self, cal: CalendarStore, recipient: Recipient, rule: Rule, event: CalendarEvent, alert: StoredAlert) -> None:
        message = AlertMessage(event.title, event.start, rule.lead_minutes, event.sources)
        try:
            await self._channels[rule.channel].send(message, recipient, cal)
        except Exception as error:  # one failing channel must not stop the others
            await cal.set_alert_status(alert, "failed")
            await self._report(f"calendar {rule.channel} alert failed: {type(error).__name__}")
