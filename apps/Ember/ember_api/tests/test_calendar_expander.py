from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.services.calendar_expander import expand, merge

NY = ZoneInfo("America/New_York")


def utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def cal(body: str) -> str:
    return "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//t//EN\n" + body + "END:VCALENDAR\n"


def test_recurrence_with_a_moved_occurrence() -> None:
    ics = cal("""BEGIN:VEVENT
UID:a1
DTSTART:20261026T090000Z
DTEND:20261026T100000Z
RRULE:FREQ=DAILY;COUNT=3
SUMMARY:Standup
END:VEVENT
BEGIN:VEVENT
UID:a1
RECURRENCE-ID:20261027T090000Z
DTSTART:20261027T110000Z
DTEND:20261027T120000Z
SUMMARY:Standup moved
END:VEVENT
""")
    got = expand(ics, utc(2026, 10, 26), utc(2026, 10, 30), NY)
    assert [(e.title, e.start.hour) for e in got] == [("Standup", 9), ("Standup moved", 11), ("Standup", 9)]


def test_cancelled_events_are_dropped() -> None:
    ics = cal("BEGIN:VEVENT\nUID:d\nDTSTART:20261028T130000Z\nDTEND:20261028T140000Z\nSTATUS:CANCELLED\nSUMMARY:x\nEND:VEVENT\n")
    assert expand(ics, utc(2026, 10, 26), utc(2026, 10, 30), NY) == []


def test_all_day_and_floating_events_use_the_account_zone() -> None:
    ics = cal("""BEGIN:VEVENT
UID:b
DTSTART;VALUE=DATE:20261026
SUMMARY:Holiday
END:VEVENT
BEGIN:VEVENT
UID:c
DTSTART:20261026T130000
DTEND:20261026T140000
SUMMARY:Floating
END:VEVENT
""")
    got = {e.title: e for e in expand(ics, utc(2026, 10, 26), utc(2026, 10, 28), NY)}
    assert got["Holiday"].all_day and got["Holiday"].start == utc(2026, 10, 26, 4)
    assert not got["Floating"].all_day and got["Floating"].start == utc(2026, 10, 26, 17)


def test_a_weekly_event_follows_daylight_saving_in_its_own_zone() -> None:
    ics = cal("""BEGIN:VEVENT
UID:w
DTSTART;TZID=America/New_York:20261026T090000
DTEND;TZID=America/New_York:20261026T100000
RRULE:FREQ=WEEKLY;COUNT=2
SUMMARY:Weekly
END:VEVENT
""")
    got = expand(ics, utc(2026, 10, 26), utc(2026, 11, 4), NY)
    assert [e.start.hour for e in got] == [13, 14]


def test_merge_joins_the_same_event_from_two_feeds() -> None:
    ics = cal("BEGIN:VEVENT\nUID:z\nDTSTART:20261026T090000Z\nDTEND:20261026T100000Z\nSUMMARY:Sync\nEND:VEVENT\n")
    a = expand(ics, utc(2026, 10, 26), utc(2026, 10, 27), NY, "Work")
    b = expand(ics, utc(2026, 10, 26), utc(2026, 10, 27), NY, "Team")
    got = merge([a, b])
    assert len(got) == 1 and got[0].sources == ("Work", "Team")


def test_event_key_is_stable() -> None:
    ics = cal("BEGIN:VEVENT\nUID:k\nDTSTART:20261026T090000Z\nDTEND:20261026T100000Z\nSUMMARY:K\nEND:VEVENT\n")
    (event,) = expand(ics, utc(2026, 10, 26), utc(2026, 10, 27), NY)
    assert event.key == "k|2026-10-26T09:00:00+00:00"
