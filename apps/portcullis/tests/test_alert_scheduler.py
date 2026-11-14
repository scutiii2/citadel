from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from src.config import CalendarSettings
from src.services.alert_channels import Recipient
from src.services.alert_scheduler import AlertScheduler, is_due
from src.services.calendar_events import EventResult
from src.services.calendar_expander import CalendarEvent
from src.services.calendar_store import CalendarStore
from src.services.secret_box import SecretBox
from tests.conftest import FakeDbGateway

BOX = SecretBox(Fernet.generate_key().decode("ascii"))
SETTINGS = CalendarSettings()
START = datetime(2026, 10, 26, 10, tzinfo=timezone.utc)


def at(minute: int, hour: int = 9) -> datetime:
    return datetime(2026, 10, 26, hour, minute, tzinfo=timezone.utc)


def event(uid="e1", all_day=False) -> CalendarEvent:
    return CalendarEvent(uid, "Standup", START, START + timedelta(hours=1), all_day, "", "", ("Work",))


class FakeEvents:
    def __init__(self, *events: CalendarEvent) -> None:
        self.found, self.calls = list(events), 0

    async def events(self, cal, start, end) -> EventResult:
        self.calls += 1
        return EventResult(self.found, [])


class Recorder:
    def __init__(self, fail: bool = False) -> None:
        self.sent, self.fail = [], fail

    async def send(self, message, recipient, cal) -> None:
        if self.fail:
            raise RuntimeError("boom")
        self.sent.append((message.title, message.lead_minutes))


def build(events, channels, *, recipient="ok", switches=None, errors=None):
    gateway = FakeDbGateway()
    cal = CalendarStore(gateway, "u1", BOX, SETTINGS)

    async def lookup(uid):
        return Recipient(uid, "ada@example.com") if recipient == "ok" else None

    async def read_switches():
        return switches if switches is not None else {"calendar_inapp": True, "calendar_email": True, "calendar_push": True}

    async def on_error(message):
        errors.append(message)

    scheduler = AlertScheduler(
        store=gateway, box=BOX, events=events, channels=channels, settings=SETTINGS,
        lookup=lookup, switches=read_switches, on_error=on_error if errors is not None else None,
    )
    return cal, scheduler


def test_is_due_window() -> None:
    assert not is_due(START, 15, at(44), 5)
    assert is_due(START, 15, at(45), 5) and is_due(START, 15, at(50), 5)
    assert not is_due(START, 15, at(51), 5)
    assert not is_due(START, 1, at(0, 10), 5)  # never after the event started


def test_an_alert_fires_once_inside_its_window() -> None:
    inapp = Recorder()
    cal, scheduler = build(FakeEvents(event()), {"inapp": inapp})
    asyncio.run(cal.add_rule("inapp", 15))
    for minute in (44, 45, 46, 47):
        asyncio.run(scheduler.tick(at(minute)))
    assert inapp.sent == [("Standup", 15)]
    assert len(asyncio.run(cal.unseen_alerts())) == 1


def test_a_missed_window_is_dropped_not_sent_late() -> None:
    inapp = Recorder()
    cal, scheduler = build(FakeEvents(event()), {"inapp": inapp})
    asyncio.run(cal.add_rule("inapp", 15))
    asyncio.run(scheduler.tick(at(55)))
    assert inapp.sent == []


def test_each_rule_fires_on_its_own_channel() -> None:
    inapp, email = Recorder(), Recorder()
    cal, scheduler = build(FakeEvents(event()), {"inapp": inapp, "email": email})
    asyncio.run(cal.add_rule("inapp", 15))
    asyncio.run(cal.add_rule("email", 30))
    asyncio.run(scheduler.tick(at(30)))
    asyncio.run(scheduler.tick(at(45)))
    assert (email.sent, inapp.sent) == ([("Standup", 30)], [("Standup", 15)])


def test_a_channel_the_admin_switched_off_does_not_fire() -> None:
    email = Recorder()
    cal, scheduler = build(FakeEvents(event()), {"email": email}, switches={"calendar_email": False})
    asyncio.run(cal.add_rule("email", 30))
    asyncio.run(scheduler.tick(at(30)))
    assert email.sent == [] and asyncio.run(cal.unseen_alerts()) == []


def test_a_failing_channel_is_marked_reported_and_does_not_stop_others() -> None:
    errors: list[str] = []
    email, inapp = Recorder(fail=True), Recorder()
    cal, scheduler = build(FakeEvents(event()), {"email": email, "inapp": inapp}, errors=errors)
    asyncio.run(cal.add_rule("email", 15))
    asyncio.run(cal.add_rule("inapp", 15))
    asyncio.run(scheduler.tick(at(45)))
    assert inapp.sent == [("Standup", 15)]
    assert errors == ["calendar email alert failed: RuntimeError"]


def test_all_day_events_and_unknown_or_forbidden_accounts_are_skipped() -> None:
    inapp = Recorder()
    cal, scheduler = build(FakeEvents(event(all_day=True)), {"inapp": inapp})
    asyncio.run(cal.add_rule("inapp", 15))
    asyncio.run(scheduler.tick(at(45)))
    assert inapp.sent == []
    cal2, scheduler2 = build(FakeEvents(event()), {"inapp": inapp}, recipient="none")
    asyncio.run(cal2.add_rule("inapp", 15))
    asyncio.run(scheduler2.tick(at(45)))
    assert inapp.sent == []


def test_events_are_expanded_once_per_refresh_period() -> None:
    events = FakeEvents(event())
    cal, scheduler = build(events, {"inapp": Recorder()})
    asyncio.run(cal.add_rule("inapp", 15))
    for minute in (40, 41, 42):
        asyncio.run(scheduler.tick(at(minute)))
    assert events.calls == 1
    asyncio.run(scheduler.tick(at(52)))
    assert events.calls == 2
