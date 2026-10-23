"""Turns ICS text into concrete events in a time range. Parsing is CPU work: callers run it in a thread."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

MAX_TEXT = 4000


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    title: str
    start: datetime  # aware, UTC
    end: datetime  # aware, UTC
    all_day: bool
    location: str
    description: str
    sources: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.uid}|{self.start.isoformat()}"


def _utc(value: date | datetime, zone: ZoneInfo) -> datetime:
    """A date is midnight in the account's zone; a floating time is read in that zone too."""
    if not isinstance(value, datetime):
        value = datetime.combine(value, time.min)
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone)
    return value.astimezone(timezone.utc)


def expand(ics: bytes | str, start: datetime, end: datetime, zone: ZoneInfo, source: str = "") -> list[CalendarEvent]:
    """Events overlapping [start, end) (aware datetimes). Cancelled ones are dropped."""
    calendar = icalendar.Calendar.from_ical(ics)
    events: list[CalendarEvent] = []
    for item in recurring_ical_events.of(calendar).between(start, end):
        if str(item.get("STATUS", "")).upper() == "CANCELLED":
            continue
        begin = item.start
        first = _utc(begin, zone)
        last = max(_utc(item.end, zone), first)
        events.append(CalendarEvent(
            uid=str(item.get("UID", "")),
            title=str(item.get("SUMMARY", "") or "(no title)"),
            start=first,
            end=last,
            all_day=not isinstance(begin, datetime),
            location=str(item.get("LOCATION", "") or "")[:MAX_TEXT],
            description=str(item.get("DESCRIPTION", "") or "")[:MAX_TEXT],
            sources=(source,) if source else (),
        ))
    return sorted(events, key=lambda e: (e.start, e.title))


def merge(lists: list[list[CalendarEvent]]) -> list[CalendarEvent]:
    """One entry per event that several feeds share (same uid, or same title when it has none)."""
    merged: dict[tuple, CalendarEvent] = {}
    for events in lists:
        for event in events:
            key = (event.uid or event.title, event.start, event.end)
            seen = merged.get(key)
            if seen is None:
                merged[key] = event
            else:
                names = seen.sources + tuple(s for s in event.sources if s not in seen.sources)
                merged[key] = replace(seen, sources=names)
    return sorted(merged.values(), key=lambda e: (e.start, e.title))
