# Calendar schedule and alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each Ember account keeps a private, read-only schedule built from ICS links and gets alerts (in-app, email, web push) before events start, driven by per-account alarm rules.

**Architecture:** Everything runs in ember_api. Feeds, alarm rules, push subscriptions, alerts and the timezone are db_gateway documents (no Alembic migration). A `FeedCache` fetches ICS feeds safely, `calendar_expander` turns them into concrete events, and an `AlertScheduler` loop (started in the app lifespan) fires each (rule, event) pair at most once through `Channel` classes. ember_web gets a `features/calendar` page built on FullCalendar; ember_admin gets three channel switches.

**Tech Stack:** Python 3.11+, FastAPI, httpx, `icalendar`, `recurring-ical-events`, `pywebpush`, db_gateway `DocumentStore`, Fernet `SecretBox`; Vue 3 + TypeScript, Pinia, `@fullcalendar/*`, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-24-calendar-schedule-design.md`

## Global Constraints

- Animations always play: never add a reduced-motion setting, `prefers-reduced-motion` query or test (repo rule in `AGENTS.md`).
- Feed URLs are bearer secrets: encrypted with `SecretBox`, never returned by the API, never logged. Log feed names only.
- Feed links must be `https://` (`webcal:` is rewritten to `https:`); every fetch and every redirect hop is checked against private, loopback, link-local and multicast addresses unless `calendar.allow_private_urls` is true.
- Defaults (copy exactly): `tick_seconds` 30, `feed_refresh_minutes` 10, `lookahead_hours` 48, `late_grace_minutes` 5, `max_feeds_per_account` 10, `max_alarm_rules` 10, `max_ics_bytes` 5242880, `fetch_timeout_s` 15, `allow_private_urls` false.
- New accounts get one default rule: channel `inapp`, 15 minutes. Lead time is 1 to 1440 minutes.
- An alert fires at most once per (rule, event): `DocumentStore.create` is the lock. All-day events never alert. Alerts older than 7 days are deleted.
- POST bodies are JSON only (existing `JsonOnlyMiddleware`). Foreign ids answer 404.
- Permission `calendar.use` is added to `ALL_PERMISSIONS` only (it syncs to the DB at startup; Administrator gets it automatically; not in the default role).
- Admin channel switches are `app_settings` booleans `calendar_inapp`, `calendar_email`, `calendar_push`, default true.
- ember_api tests use sync `def test_...` and `asyncio.run(...)` (no pytest-asyncio). Run them from `apps/Ember/ember_api` with `./.venv_ember_api/Scripts/python.exe -m pytest <path> -q`.
- ember_web / ember_admin: radius only through `--radius-*`, colors only through `style.css` tokens (except user-chosen feed colors, which are data). Shared code (`api`, `stores`, `composables`, `utils`, `components`) must not import from `features/` (`architecture.test.ts`). Checks: `npx vue-tsc -b`, `npm test`.
- Paths below are relative to the repo root `D:\User\Documents\Programming\Python\Citadel` unless they start with a shell `cd`.

## File Structure

ember_api (`apps/Ember/ember_api/`):
- Create `src/services/calendar_expander.py` — ICS text to `CalendarEvent`s; `merge`.
- Create `src/services/calendar_fetcher.py` — `clean_feed_url`, `FeedError`, `CalendarFetcher`.
- Create `src/services/calendar_store.py` — all db_gateway documents; errors; `purge_owner`; `owners_with_rules`.
- Create `src/services/calendar_events.py` — `FeedCache`, `EventSource`, `EventResult`.
- Create `src/services/vapid.py` — VAPID key pair in `.env`.
- Create `src/services/alert_channels.py` — `AlertMessage`, `Recipient`, `Channel`, `InAppChannel`, `EmailChannel`, `PushChannel`.
- Create `src/services/alert_scheduler.py` — `is_due`, `AlertScheduler`.
- Create `src/services/calendar_runtime.py` — wiring, `CalendarRuntime`.
- Create `src/routes/calendar.py` — `/api/calendar`.
- Create `src/services/email_templates/calendar_alert.txt`.
- Modify `pyproject.toml`, `src/config.py`, `configs/config_app.json.example`, `src/services/permissions.py`, `src/services/settings_service.py`, `src/services/email_service.py`, `src/services/config_validation.py`, `src/routes/admin.py`, `src/app.py`, `tests/conftest.py`, `tests/test_hidden_pages.py`, `README.md`.
- Create tests: `tests/test_calendar_config.py`, `test_calendar_expander.py`, `test_calendar_fetcher.py`, `test_calendar_store.py`, `test_calendar_events.py`, `test_vapid.py`, `test_alert_channels.py`, `test_alert_scheduler.py`, `test_calendar_routes.py`.

ember_web (`apps/Ember/ember_web/`):
- Create `src/features/calendar/api/CalendarClient.ts` (+ test).
- Create `src/features/calendar/utils/eventDetails.ts` (+ test), `utils/palette.ts`.
- Create `src/features/calendar/stores/calendar.ts` (+ test).
- Create `src/features/calendar/CalendarView.vue`, `components/FeedsPanel.vue`, `components/AlertRulesPanel.vue`, `components/EventDialog.vue`, `components/AlertToasts.vue`.
- Create `src/features/calendar/composables/usePushSubscription.ts` (+ test), `useAlertPoller.ts` (+ test).
- Create `public/push-sw.js`.
- Modify `package.json`, `vite.config.ts`, `src/router/index.ts`, `src/router/pages.ts`, `src/App.vue`, `e2e/fakeApi.ts`; create `e2e/calendar.spec.ts`.

ember_admin (`apps/Ember/ember_admin/`): modify `src/api/SettingsClient.ts`; create `src/components/admin/CalendarChannelsPanel.vue` (+ test); mount it beside `SettingsPanel`.

---

### Task 1: Dependencies, config block, permission, channel switches

**Files:**
- Modify: `apps/Ember/ember_api/pyproject.toml`
- Modify: `apps/Ember/ember_api/src/config.py`
- Modify: `apps/Ember/ember_api/configs/config_app.json.example`
- Modify: `apps/Ember/ember_api/src/services/permissions.py`
- Modify: `apps/Ember/ember_api/src/services/settings_service.py`
- Modify: `apps/Ember/ember_api/tests/test_hidden_pages.py:100`
- Test: `apps/Ember/ember_api/tests/test_calendar_config.py`

**Interfaces:**
- Produces: `CalendarSettings` (fields: `enabled`, `tick_seconds`, `feed_refresh_minutes`, `lookahead_hours`, `late_grace_minutes`, `max_feeds_per_account`, `max_alarm_rules`, `max_ics_bytes`, `fetch_timeout_s`, `allow_private_urls`, `push_contact`; `CalendarSettings.from_config(raw: dict)`); `Settings.calendar`; `permissions.CALENDAR_USE = "calendar.use"`; `settings_service.CALENDAR_CHANNELS = ("calendar_inapp", "calendar_email", "calendar_push")`.

- [ ] **Step 1: Write the failing tests**

Create `apps/Ember/ember_api/tests/test_calendar_config.py`:

```python
"""Calendar config block, permission and admin channel switches."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import CalendarSettings
from src.services.permissions import CALENDAR_USE, is_known_permission
from tests.test_registration import as_admin


def test_defaults_match_the_spec() -> None:
    s = CalendarSettings.from_config({})
    assert (s.enabled, s.tick_seconds, s.feed_refresh_minutes, s.lookahead_hours) == (True, 30, 10, 48)
    assert (s.late_grace_minutes, s.max_feeds_per_account, s.max_alarm_rules) == (5, 10, 10)
    assert (s.max_ics_bytes, s.fetch_timeout_s, s.allow_private_urls) == (5242880, 15, False)


def test_values_are_read_and_validated() -> None:
    assert CalendarSettings.from_config({"tick_seconds": 5, "enabled": False}).tick_seconds == 5
    for bad in ({"tick_seconds": 0}, {"max_ics_bytes": -1}, {"push_contact": "nobody"}):
        with pytest.raises(ValueError):
            CalendarSettings.from_config(bad)


def test_permission_is_known() -> None:
    assert is_known_permission(CALENDAR_USE) and CALENDAR_USE == "calendar.use"


def test_administrator_holds_calendar_use(client: TestClient) -> None:
    as_admin(client)
    assert CALENDAR_USE in client.get("/api/auth/me").json()["permissions"]


def test_channel_switches_default_on_and_admin_can_flip(client: TestClient) -> None:
    as_admin(client)
    body = client.get("/api/settings").json()
    assert [body[n] for n in ("calendar_inapp", "calendar_email", "calendar_push")] == [True, True, True]
    assert client.put("/api/admin/settings/calendar_push", json={"value": False}).json() == {"calendar_push": False}
    assert client.get("/api/settings").json()["calendar_push"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_config.py -q`
Expected: FAIL (`ImportError: cannot import name 'CalendarSettings'`).

- [ ] **Step 3: Add dependencies and install them**

In `pyproject.toml`, after the `"cryptography>=42",` line add:

```toml
    # Calendar: read ICS feeds, expand recurrences, send web push alerts.
    "icalendar>=6.0",
    "recurring-ical-events>=3.0",
    "pywebpush>=2.0",
    # Time zone database for zoneinfo on Windows.
    "tzdata>=2024.1",
```

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pip install -e .`
Expected: installs icalendar, recurring-ical-events, pywebpush, tzdata without error.

- [ ] **Step 4: Implement config, permission, switches**

In `src/config.py`, after `DbGatewaySettings` add:

```python
@dataclass(frozen=True)
class CalendarSettings:
    """config_app.json's "calendar" block: ICS schedule feeds and the alerts before events."""

    enabled: bool = True
    tick_seconds: int = 30
    feed_refresh_minutes: int = 10
    lookahead_hours: int = 48
    late_grace_minutes: int = 5
    max_feeds_per_account: int = 10
    max_alarm_rules: int = 10
    max_ics_bytes: int = 5 * 1024 * 1024
    fetch_timeout_s: int = 15
    allow_private_urls: bool = False
    # The "sub" claim of web push messages; push services may contact it.
    push_contact: str = "mailto:admin@example.com"

    @classmethod
    def from_config(cls, raw: dict) -> CalendarSettings:
        positive = (
            "tick_seconds", "feed_refresh_minutes", "lookahead_hours", "late_grace_minutes",
            "max_feeds_per_account", "max_alarm_rules", "max_ics_bytes", "fetch_timeout_s",
        )
        numbers = {name: int(raw.get(name, getattr(cls, name))) for name in positive}
        for name, value in numbers.items():
            if value < 1:
                raise ValueError(f"calendar.{name} must be at least 1")
        contact = str(raw.get("push_contact") or cls.push_contact)
        if not contact.startswith(("mailto:", "https://")):
            raise ValueError("calendar.push_contact must start with mailto: or https://")
        return cls(
            enabled=bool(raw.get("enabled", True)),
            allow_private_urls=bool(raw.get("allow_private_urls", False)),
            push_contact=contact,
            **numbers,
        )
```

In `Settings` add the field after `db_gateway`:

```python
    calendar: CalendarSettings = field(default_factory=CalendarSettings)
```

In `load_settings()` add after the `db_gateway=` line:

```python
        calendar=CalendarSettings.from_config(raw.get("calendar", {})),
```

In `configs/config_app.json.example`, change the final `"backup"` block's closing so the file ends:

```json
  "backup": {
    "enabled": true,
    "keep": 14,
    "every_hours": 24
  },
  "calendar": {
    "enabled": true,
    "tick_seconds": 30,
    "feed_refresh_minutes": 10,
    "lookahead_hours": 48,
    "late_grace_minutes": 5,
    "max_feeds_per_account": 10,
    "max_alarm_rules": 10,
    "max_ics_bytes": 5242880,
    "fetch_timeout_s": 15,
    "allow_private_urls": false,
    "push_contact": "mailto:admin@example.com"
  }
}
```

In `src/services/permissions.py` add after `BRAIN_INSTANCE_PUBLISH = ...`:

```python
CALENDAR_USE = "calendar.use"
```

and in `ALL_PERMISSIONS` add (first entry, after the opening brace line):

```python
    CALENDAR_USE: "Keep a read-only schedule from ICS links and get alerts before events",
```

In `src/services/settings_service.py` replace the `BOOLEAN_SETTINGS` line with:

```python
# Which alert channels the calendar may use for everyone; each is on until an administrator switches it off.
CALENDAR_CHANNELS = ("calendar_inapp", "calendar_email", "calendar_push")

BOOLEAN_SETTINGS: dict[str, bool] = {FORCE_TOOL_APPROVAL: False, **{name: True for name in CALENDAR_CHANNELS}}
```

In `tests/test_hidden_pages.py` line 100 replace the expected dict with:

```python
    assert client.get("/api/settings").json() == {
        "force_tool_approval": False, "calendar_inapp": True, "calendar_email": True, "calendar_push": True,
    }
```

- [ ] **Step 5: Run the tests**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_config.py tests/test_hidden_pages.py tests/test_forced_approval.py tests/test_permission_split.py -q`
Expected: PASS. If another test asserts the exact permission list or settings dict, add the new names to it.

- [ ] **Step 6: Commit**

```bash
git add apps/Ember/ember_api/pyproject.toml apps/Ember/ember_api/src/config.py apps/Ember/ember_api/configs/config_app.json.example apps/Ember/ember_api/src/services/permissions.py apps/Ember/ember_api/src/services/settings_service.py apps/Ember/ember_api/tests/test_calendar_config.py apps/Ember/ember_api/tests/test_hidden_pages.py
git commit -m "feat(calendar): config block, calendar.use permission and channel switches"
```

---

### Task 2: Event expander

**Files:**
- Create: `apps/Ember/ember_api/src/services/calendar_expander.py`
- Test: `apps/Ember/ember_api/tests/test_calendar_expander.py`

**Interfaces:**
- Produces: `CalendarEvent(uid, title, start, end, all_day, location, description, sources)` frozen dataclass with `.key` (`"<uid>|<start iso>"`); `expand(ics: bytes | str, start: datetime, end: datetime, zone: ZoneInfo, source: str = "") -> list[CalendarEvent]` (start/end aware; result times aware UTC, sorted); `merge(lists: list[list[CalendarEvent]]) -> list[CalendarEvent]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_calendar_expander.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_expander.py -q`
Expected: FAIL (`ModuleNotFoundError: src.services.calendar_expander`).

- [ ] **Step 3: Implement**

Create `src/services/calendar_expander.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_expander.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_api/src/services/calendar_expander.py apps/Ember/ember_api/tests/test_calendar_expander.py
git commit -m "feat(calendar): expand ICS feeds into events"
```

---

### Task 3: Safe feed fetcher

**Files:**
- Create: `apps/Ember/ember_api/src/services/calendar_fetcher.py`
- Test: `apps/Ember/ember_api/tests/test_calendar_fetcher.py`

**Interfaces:**
- Produces: `FeedError(Exception)`; `clean_feed_url(raw: str) -> str`; `FetchResult(body: bytes | None, etag: str | None)` with `.not_modified`; `Resolver = Callable[[str, int], Awaitable[list[str]]]`; `system_resolver`; `CalendarFetcher(client: httpx.AsyncClient, *, max_bytes: int, allow_private_urls: bool = False, resolve: Resolver = system_resolver)` with `async fetch(url: str, etag: str | None = None) -> FetchResult`. The client must NOT follow redirects.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_calendar_fetcher.py`:

```python
from __future__ import annotations

import asyncio

import httpx
import pytest

from src.services.calendar_fetcher import CalendarFetcher, FeedError, clean_feed_url

PUBLIC = ["93.184.216.34"]


async def public(host: str, port: int) -> list[str]:
    return PUBLIC


async def loopback(host: str, port: int) -> list[str]:
    return ["127.0.0.1"]


def fetcher(handler, resolve=public, max_bytes: int = 1000, **kw) -> CalendarFetcher:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return CalendarFetcher(client, max_bytes=max_bytes, resolve=resolve, **kw)


def test_webcal_becomes_https_and_other_links_are_refused() -> None:
    assert clean_feed_url(" webcal://x.com/a.ics ") == "https://x.com/a.ics"
    for bad in ("http://x.com/a.ics", "ftp://x.com", "", "https://u:p@x.com/a"):
        with pytest.raises(FeedError):
            clean_feed_url(bad)


def test_fetch_returns_body_and_etag() -> None:
    f = fetcher(lambda r: httpx.Response(200, content=b"ICS", headers={"etag": '"1"'}))
    got = asyncio.run(f.fetch("https://x.com/a.ics"))
    assert (got.body, got.etag, got.not_modified) == (b"ICS", '"1"', False)


def test_304_is_not_modified_and_the_etag_is_sent() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["inm"] = request.headers.get("if-none-match")
        return httpx.Response(304)

    got = asyncio.run(fetcher(handler).fetch("https://x.com/a.ics", '"1"'))
    assert got.not_modified and seen["inm"] == '"1"'


def test_private_addresses_are_refused_unless_allowed() -> None:
    ok = lambda r: httpx.Response(200, content=b"ICS")  # noqa: E731
    with pytest.raises(FeedError, match="not allowed"):
        asyncio.run(fetcher(ok, resolve=loopback).fetch("https://x.com/a.ics"))
    allowed = fetcher(ok, resolve=loopback, allow_private_urls=True)
    assert asyncio.run(allowed.fetch("https://x.com/a.ics")).body == b"ICS"


def test_a_redirect_to_a_private_host_is_refused() -> None:
    async def resolve(host: str, port: int) -> list[str]:
        return ["127.0.0.1"] if host == "inner.local" else PUBLIC

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "x.com":
            return httpx.Response(302, headers={"location": "https://inner.local/a.ics"})
        return httpx.Response(200, content=b"secret")

    with pytest.raises(FeedError, match="not allowed"):
        asyncio.run(fetcher(handler, resolve=resolve).fetch("https://x.com/a.ics"))


def test_a_redirect_to_http_is_refused() -> None:
    f = fetcher(lambda r: httpx.Response(302, headers={"location": "http://x.com/a.ics"}))
    with pytest.raises(FeedError, match="not https"):
        asyncio.run(f.fetch("https://x.com/a.ics"))


def test_oversized_failed_and_unreachable_feeds_raise_feed_error() -> None:
    with pytest.raises(FeedError, match="too large"):
        asyncio.run(fetcher(lambda r: httpx.Response(200, content=b"x" * 2000)).fetch("https://x.com/a"))
    with pytest.raises(FeedError, match="HTTP 500"):
        asyncio.run(fetcher(lambda r: httpx.Response(500)).fetch("https://x.com/a"))

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(FeedError, match="could not be reached"):
        asyncio.run(fetcher(refuse).fetch("https://x.com/a"))
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_fetcher.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

Create `src/services/calendar_fetcher.py`:

```python
"""Fetching an ICS feed safely: https only, public addresses only, capped in size.

shortcut: the address is checked, then httpx connects by name, so a DNS answer that changes between
the two calls (rebinding) is not blocked. Pin the checked address in the transport if that matters.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

MAX_URL = 2000
MAX_REDIRECTS = 3

Resolver = Callable[[str, int], Awaitable[list[str]]]


class FeedError(Exception):
    """A feed that cannot be used. The message is safe to show and never holds the URL."""


def clean_feed_url(raw: str) -> str:
    """`webcal:` becomes `https:`; anything but https is refused."""
    url = raw.strip()
    if url.lower().startswith("webcal:"):
        url = "https:" + url[len("webcal:"):]
    parts = urlsplit(url)
    if not url or len(url) > MAX_URL or parts.scheme.lower() != "https" or not parts.hostname:
        raise FeedError("Enter an https:// or webcal:// link")
    if parts.username is not None or parts.password is not None:
        raise FeedError("The link must not contain a user name or password")
    return url


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


@dataclass(frozen=True)
class FetchResult:
    body: bytes | None  # None when the server said "not modified"
    etag: str | None

    @property
    def not_modified(self) -> bool:
        return self.body is None


class CalendarFetcher:
    """`client` must not follow redirects: this class follows them itself so that every hop is checked."""

    def __init__(
        self, client: httpx.AsyncClient, *, max_bytes: int, allow_private_urls: bool = False,
        resolve: Resolver = system_resolver,
    ) -> None:
        self._client = client
        self._max_bytes = max_bytes
        self._allow_private = allow_private_urls
        self._resolve = resolve

    async def _check_host(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme.lower() != "https":
            raise FeedError("The feed redirected to a link that is not https")
        if self._allow_private:
            return
        try:
            addresses = await self._resolve(parts.hostname or "", parts.port or 443)
        except OSError:
            raise FeedError("The feed's address could not be found") from None
        for address in addresses:
            ip = ipaddress.ip_address(address.split("%")[0])
            if not ip.is_global or ip.is_multicast:
                raise FeedError("That address is not allowed")

    async def fetch(self, url: str, etag: str | None = None) -> FetchResult:
        headers = {"Accept": "text/calendar, */*;q=0.5"}
        if etag:
            headers["If-None-Match"] = etag
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            await self._check_host(current)
            try:
                async with self._client.stream("GET", current, headers=headers) as response:
                    if response.status_code == 304:
                        return FetchResult(None, etag)
                    if response.is_redirect:
                        target = response.headers.get("location", "")
                        if not target:
                            raise FeedError("The feed redirected without a target")
                        current = urljoin(current, target)
                        continue
                    if response.status_code != 200:
                        raise FeedError(f"The feed answered HTTP {response.status_code}")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            raise FeedError("The feed is too large")
                    return FetchResult(bytes(body), response.headers.get("etag"))
            except httpx.HTTPError:
                raise FeedError("The feed could not be reached") from None
        raise FeedError("The feed redirected too many times")
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_fetcher.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_api/src/services/calendar_fetcher.py apps/Ember/ember_api/tests/test_calendar_fetcher.py
git commit -m "feat(calendar): fetch ICS feeds with an address guard and size cap"
```

---

### Task 4: Calendar store on db_gateway

**Files:**
- Create: `apps/Ember/ember_api/src/services/calendar_store.py`
- Test: `apps/Ember/ember_api/tests/test_calendar_store.py`

**Interfaces:**
- Consumes: `CalendarSettings` (Task 1), `CalendarEvent` (Task 2), `clean_feed_url`/`FeedError` (Task 3), `SecretBox`, `DocumentStore`.
- Produces (all in `src/services/calendar_store.py`):
  - Constants `FEEDS, RULES, PUSH, ALERTS, PREFS, COLLECTIONS, CHANNELS = ("inapp","email","push")`, `MIN_LEAD = 1`, `MAX_LEAD = 1440`.
  - Errors `CalendarError` (`status = 400`), `CalendarInvalid(CalendarError)`, `CalendarNotFound` (404), `CalendarLimit` (409).
  - Dataclasses `Feed(id, name, color, url_enc, enabled, last_fetch_at, last_error, created_at)`, `Rule(id, channel, lead_minutes, enabled)`, `PushSubscription(key, endpoint, p256dh, auth)` with `.info() -> dict`, `StoredAlert(id, title, start_utc, channel, status, state, created_at)`.
  - `CalendarStore(store: DocumentStore, owner: str, box: SecretBox, limits: CalendarSettings)` with methods: `feeds()`, `feed(id)`, `add_feed(name, url, color)`, `update_feed(id, *, name=None, color=None, enabled=None, url=None)`, `delete_feed(id)`, `feed_url(feed)`, `feed_key(feed)`, `record_fetch(feed_id, *, error)`, `rules()`, `add_rule(channel, lead_minutes)`, `update_rule(rule_id, *, channel=None, lead_minutes=None, enabled=None)`, `delete_rule(rule_id)`, `timezone_name()`, `timezone_saved()`, `set_timezone(name)`, `zone()`, `push_subscriptions()`, `add_push(endpoint, p256dh, auth)`, `remove_push(endpoint)`, `remove_push_key(key)`, `create_alert(rule, event)`, `set_alert_status(alert, status)`, `unseen_alerts()`, `mark_seen(alert_id)`, `prune_alerts(now)`.
  - Module functions `purge_owner(store, owner_uid) -> int`, `owners_with_rules(store) -> set[str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_calendar_store.py`:

```python
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet

from src.config import CalendarSettings
from src.services.calendar_expander import CalendarEvent
from src.services.calendar_store import (
    ALERTS, CalendarInvalid, CalendarLimit, CalendarNotFound, CalendarStore, owners_with_rules, purge_owner,
)
from src.services.secret_box import SecretBox
from tests.conftest import FakeDbGateway

URL = "https://outlook.office365.com/owa/calendar/abc/private/reachcalendar.ics"


def make(gateway: FakeDbGateway, owner: str = "u1", **limits) -> CalendarStore:
    return CalendarStore(gateway, owner, SecretBox(Fernet.generate_key().decode("ascii")), CalendarSettings(**limits))


def event(uid: str = "e1", hour: int = 10) -> CalendarEvent:
    start = datetime(2026, 10, 26, hour, tzinfo=timezone.utc)
    return CalendarEvent(uid, "Standup", start, start + timedelta(hours=1), False, "", "")


def test_feed_url_is_encrypted_and_never_stored_in_clear() -> None:
    gateway = FakeDbGateway()
    cal = make(gateway)
    feed = asyncio.run(cal.add_feed("Work", "webcal://outlook.office365.com/x.ics", "#2563eb"))
    assert "outlook.office365.com" not in str(gateway.records)
    assert cal.feed_url(feed) == "https://outlook.office365.com/x.ics"


def test_feed_validation_limits_and_ownership() -> None:
    gateway = FakeDbGateway()
    cal = make(gateway, max_feeds_per_account=1)
    asyncio.run(cal.add_feed("Work", URL, "#2563eb"))
    with pytest.raises(CalendarLimit):
        asyncio.run(cal.add_feed("Two", URL, "#2563eb"))
    other = make(gateway, owner="u2")
    for name, url, color in (("", URL, "#2563eb"), ("x", "http://a.com/x.ics", "#2563eb"), ("x", URL, "blue")):
        with pytest.raises(CalendarInvalid):
            asyncio.run(other.add_feed(name, url, color))
    feed = asyncio.run(cal.feeds())[0]
    with pytest.raises(CalendarNotFound):
        asyncio.run(other.feed(feed.id))
    assert asyncio.run(other.feeds()) == []


def test_update_and_delete_a_feed() -> None:
    cal = make(FakeDbGateway())
    feed = asyncio.run(cal.add_feed("Work", URL, "#2563eb"))
    changed = asyncio.run(cal.update_feed(feed.id, name="Job", enabled=False))
    assert (changed.name, changed.enabled) == ("Job", False)
    asyncio.run(cal.record_fetch(feed.id, error="The feed answered HTTP 500"))
    assert asyncio.run(cal.feed(feed.id)).last_error == "The feed answered HTTP 500"
    asyncio.run(cal.delete_feed(feed.id))
    with pytest.raises(CalendarNotFound):
        asyncio.run(cal.delete_feed(feed.id))


def test_first_visit_seeds_one_default_rule_and_deleting_it_sticks() -> None:
    cal = make(FakeDbGateway())
    (rule,) = asyncio.run(cal.rules())
    assert (rule.channel, rule.lead_minutes, rule.enabled) == ("inapp", 15, True)
    asyncio.run(cal.delete_rule(rule.id))
    assert asyncio.run(cal.rules()) == []


def test_rule_validation() -> None:
    cal = make(FakeDbGateway(), max_alarm_rules=2)
    asyncio.run(cal.add_rule("email", 30))
    for channel, lead in (("sms", 10), ("email", 0), ("email", 1441), ("email", 30)):
        with pytest.raises(CalendarInvalid):
            asyncio.run(cal.add_rule(channel, lead))
    asyncio.run(cal.add_rule("push", 5))
    with pytest.raises(CalendarLimit):
        asyncio.run(cal.add_rule("inapp", 60))
    first = asyncio.run(cal.rules())[0]
    assert asyncio.run(cal.update_rule(first.id, lead_minutes=10, enabled=False)).lead_minutes == 10


def test_timezone_defaults_to_utc_and_must_be_a_real_zone() -> None:
    cal = make(FakeDbGateway())
    assert asyncio.run(cal.timezone_name()) == "UTC" and not asyncio.run(cal.timezone_saved())
    asyncio.run(cal.set_timezone("Europe/Madrid"))
    assert asyncio.run(cal.zone()).key == "Europe/Madrid" and asyncio.run(cal.timezone_saved())
    with pytest.raises(CalendarInvalid):
        asyncio.run(cal.set_timezone("Not/AZone"))


def test_push_subscriptions_are_unique_per_endpoint_and_capped() -> None:
    cal = make(FakeDbGateway())
    asyncio.run(cal.add_push("https://push.example/a", "k", "s"))
    asyncio.run(cal.add_push("https://push.example/a", "k2", "s2"))
    (sub,) = asyncio.run(cal.push_subscriptions())
    assert sub.p256dh == "k2" and sub.info() == {"endpoint": "https://push.example/a", "keys": {"p256dh": "k2", "auth": "s2"}}
    with pytest.raises(CalendarInvalid):
        asyncio.run(cal.add_push("http://push.example/a", "k", "s"))
    asyncio.run(cal.remove_push_key(sub.key))
    assert asyncio.run(cal.push_subscriptions()) == []


def test_an_alert_is_created_once_per_rule_and_event() -> None:
    cal = make(FakeDbGateway())
    (rule,) = asyncio.run(cal.rules())
    first = asyncio.run(cal.create_alert(rule, event()))
    assert first is not None and asyncio.run(cal.create_alert(rule, event())) is None
    assert asyncio.run(cal.create_alert(rule, event(hour=11))) is not None
    assert len(asyncio.run(cal.unseen_alerts())) == 2
    asyncio.run(cal.mark_seen(first.id))
    assert len(asyncio.run(cal.unseen_alerts())) == 1
    with pytest.raises(CalendarNotFound):
        asyncio.run(cal.mark_seen("nope"))


def test_only_in_app_alerts_wait_in_the_inbox_and_failures_are_marked() -> None:
    cal = make(FakeDbGateway())
    email = asyncio.run(cal.add_rule("email", 30))
    alert = asyncio.run(cal.create_alert(email, event()))
    assert asyncio.run(cal.unseen_alerts()) == []
    asyncio.run(cal.set_alert_status(alert, "failed"))


def test_old_alerts_are_pruned() -> None:
    gateway = FakeDbGateway()
    cal = make(gateway)
    (rule,) = asyncio.run(cal.rules())
    asyncio.run(cal.create_alert(rule, event()))
    later = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=8)
    assert asyncio.run(cal.prune_alerts(later)) == 1
    assert not [k for (c, k) in gateway.records if c == ALERTS]


def test_owners_with_rules_and_purge() -> None:
    gateway = FakeDbGateway()
    a, b = make(gateway, "u1"), make(gateway, "u2")
    asyncio.run(a.add_rule("inapp", 15))
    asyncio.run(a.add_feed("Work", URL, "#2563eb"))
    disabled = asyncio.run(b.add_rule("inapp", 15))
    asyncio.run(b.update_rule(disabled.id, enabled=False))
    assert asyncio.run(owners_with_rules(gateway)) == {"u1"}
    assert asyncio.run(purge_owner(gateway, "u1")) >= 2
    assert asyncio.run(owners_with_rules(gateway)) == set()
    assert any(owner == "u2" for (_, key) in gateway.records for owner in [key.split(":")[0]])
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_store.py -q`
Expected: FAIL (`ModuleNotFoundError: src.services.calendar_store`).

- [ ] **Step 3: Implement**

Create `src/services/calendar_store.py`:

```python
"""Everything an account keeps for its schedule, as db_gateway documents.

Keys start with the account uid, so an id from another account is simply not found. Every document
repeats its own `key` and `owner`; purge and the scheduler rely on both. Updates read, change and put
the whole document (shortcut: a concurrent fetch-status write can lose a rename; harmless here).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.config import CalendarSettings
from src.db import utcnow
from src.services.calendar_expander import CalendarEvent
from src.services.calendar_fetcher import FeedError, clean_feed_url
from src.services.db_gateway import DocumentStore
from src.services.secret_box import SecretBox, SecretBoxError

FEEDS = "calendar_feeds"
RULES = "calendar_rules"
PUSH = "calendar_push"
ALERTS = "calendar_alerts"
PREFS = "calendar_prefs"
COLLECTIONS = (FEEDS, RULES, PUSH, ALERTS, PREFS)
CHANNELS = ("inapp", "email", "push")
MIN_LEAD, MAX_LEAD = 1, 1440
MAX_NAME = 60
MAX_PUSH = 10
ALERT_KEEP = timedelta(days=7)
PAGE = 100
DEFAULT_RULE = ("inapp", 15)
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_ID = re.compile(r"^[a-z0-9-]{1,80}$")


class CalendarError(Exception):
    """Something the caller can fix. The message is safe to show."""

    status = 400


class CalendarInvalid(CalendarError):
    status = 400


class CalendarNotFound(CalendarError):
    status = 404


class CalendarLimit(CalendarError):
    status = 409


def _now() -> str:
    return utcnow().isoformat(timespec="seconds")


def _digest(text: str, length: int) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > MAX_NAME:
        raise CalendarInvalid(f"Enter a name of 1 to {MAX_NAME} characters")
    return cleaned


def _clean_color(color: str) -> str:
    if not _COLOR.match(color):
        raise CalendarInvalid("Pick a color like #2563eb")
    return color.lower()


def _clean_lead(channel: str, lead_minutes: int) -> None:
    if channel not in CHANNELS:
        raise CalendarInvalid("Unknown alert type")
    if not MIN_LEAD <= lead_minutes <= MAX_LEAD:
        raise CalendarInvalid(f"Lead time must be {MIN_LEAD} to {MAX_LEAD} minutes")


@dataclass(frozen=True)
class Feed:
    id: str
    name: str
    color: str
    url_enc: str
    enabled: bool
    last_fetch_at: str | None
    last_error: str | None
    created_at: str

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Feed:
        return cls(doc["id"], doc["name"], doc["color"], doc["url_enc"], doc.get("enabled") is not False,
                   doc.get("last_fetch_at"), doc.get("last_error"), doc["created_at"])


@dataclass(frozen=True)
class Rule:
    id: str
    channel: str
    lead_minutes: int
    enabled: bool

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Rule:
        return cls(doc["id"], doc["channel"], int(doc["lead_minutes"]), doc.get("enabled") is not False)


@dataclass(frozen=True)
class PushSubscription:
    key: str
    endpoint: str
    p256dh: str
    auth: str

    def info(self) -> dict[str, Any]:
        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": self.auth}}


@dataclass(frozen=True)
class StoredAlert:
    id: str
    title: str
    start_utc: str
    channel: str
    status: str  # "sent" | "failed"
    state: str  # "new" waits in the in-app inbox, "seen" was dismissed, "done" needs no inbox
    created_at: str

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> StoredAlert:
        return cls(doc["id"], doc["title"], doc["start_utc"], doc["channel"], doc["status"], doc["state"], doc["created_at"])


class CalendarStore:
    def __init__(self, store: DocumentStore, owner: str, box: SecretBox, limits: CalendarSettings) -> None:
        self._store = store
        self._owner = owner
        self._box = box
        self._limits = limits

    # -- helpers -------------------------------------------------------------------------------
    def _key(self, *parts: str) -> str:
        return ":".join((self._owner, *parts))

    async def _mine(self, collection: str) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = await self._store.query(collection, {"owner": self._owner}, limit=PAGE, offset=offset)
            docs.extend(page)
            if len(page) < PAGE:
                return docs
            offset += PAGE

    async def _get(self, collection: str, item_id: str, missing: str) -> dict[str, Any]:
        doc = await self._store.get(collection, self._key(item_id)) if _ID.match(item_id) else None
        if doc is None:
            raise CalendarNotFound(missing)
        return doc

    async def _prefs(self) -> dict[str, Any]:
        return await self._store.get(PREFS, self._owner) or {}

    async def _set_prefs(self, **changes: Any) -> None:
        doc = {**await self._prefs(), "key": self._owner, "owner": self._owner, **changes}
        await self._store.put(PREFS, self._owner, doc)

    # -- feeds ---------------------------------------------------------------------------------
    async def feeds(self) -> list[Feed]:
        return sorted((Feed.from_doc(d) for d in await self._mine(FEEDS)), key=lambda f: (f.created_at, f.id))

    async def feed(self, feed_id: str) -> Feed:
        return Feed.from_doc(await self._get(FEEDS, feed_id, "No such calendar"))

    def feed_key(self, feed: Feed) -> str:
        return self._key(feed.id)

    def feed_url(self, feed: Feed) -> str:
        try:
            return self._box.decrypt_map(feed.url_enc)["url"]
        except (SecretBoxError, KeyError):
            raise CalendarInvalid("Its link can't be read (the secrets key changed). Edit it to set the link again.") from None

    def _encrypt_url(self, raw: str) -> str:
        try:
            return self._box.encrypt_map({"url": clean_feed_url(raw)})
        except FeedError as error:
            raise CalendarInvalid(str(error)) from None

    async def add_feed(self, name: str, url: str, color: str) -> Feed:
        if len(await self._mine(FEEDS)) >= self._limits.max_feeds_per_account:
            raise CalendarLimit(f"At most {self._limits.max_feeds_per_account} calendars are allowed")
        feed_id = uuid.uuid4().hex[:12]
        doc = {
            "key": self._key(feed_id), "owner": self._owner, "id": feed_id, "name": _clean_name(name),
            "color": _clean_color(color), "url_enc": self._encrypt_url(url), "enabled": True,
            "last_fetch_at": None, "last_error": None, "created_at": _now(),
        }
        await self._store.put(FEEDS, doc["key"], doc)
        return Feed.from_doc(doc)

    async def update_feed(
        self, feed_id: str, *, name: str | None = None, color: str | None = None,
        enabled: bool | None = None, url: str | None = None,
    ) -> Feed:
        doc = await self._get(FEEDS, feed_id, "No such calendar")
        if name is not None:
            doc["name"] = _clean_name(name)
        if color is not None:
            doc["color"] = _clean_color(color)
        if enabled is not None:
            doc["enabled"] = enabled
        if url is not None:
            doc["url_enc"] = self._encrypt_url(url)
            doc["last_error"] = None
        await self._store.put(FEEDS, doc["key"], doc)
        return Feed.from_doc(doc)

    async def delete_feed(self, feed_id: str) -> None:
        await self._get(FEEDS, feed_id, "No such calendar")
        await self._store.delete(FEEDS, self._key(feed_id))

    async def record_fetch(self, feed_id: str, *, error: str | None) -> None:
        doc = await self._store.get(FEEDS, self._key(feed_id)) if _ID.match(feed_id) else None
        if doc is None:
            return
        doc["last_error"] = error
        if error is None:
            doc["last_fetch_at"] = _now()
        await self._store.put(FEEDS, doc["key"], doc)

    # -- alarm rules ---------------------------------------------------------------------------
    async def rules(self) -> list[Rule]:
        docs = await self._mine(RULES)
        if not docs and not (await self._prefs()).get("rules_seeded"):
            await self._set_prefs(rules_seeded=True)
            await self._put_rule(*DEFAULT_RULE)
            docs = await self._mine(RULES)
        return sorted((Rule.from_doc(d) for d in docs), key=lambda r: (r.lead_minutes, r.channel, r.id))

    async def _put_rule(self, channel: str, lead_minutes: int) -> Rule:
        rule_id = uuid.uuid4().hex[:12]
        doc = {"key": self._key(rule_id), "owner": self._owner, "id": rule_id, "channel": channel,
               "lead_minutes": lead_minutes, "enabled": True}
        await self._store.put(RULES, doc["key"], doc)
        return Rule.from_doc(doc)

    async def add_rule(self, channel: str, lead_minutes: int) -> Rule:
        _clean_lead(channel, lead_minutes)
        existing = [Rule.from_doc(d) for d in await self._mine(RULES)]
        if len(existing) >= self._limits.max_alarm_rules:
            raise CalendarLimit(f"At most {self._limits.max_alarm_rules} alerts are allowed")
        if any(r.channel == channel and r.lead_minutes == lead_minutes for r in existing):
            raise CalendarInvalid("That alert already exists")
        await self._set_prefs(rules_seeded=True)
        return await self._put_rule(channel, lead_minutes)

    async def update_rule(
        self, rule_id: str, *, channel: str | None = None, lead_minutes: int | None = None, enabled: bool | None = None,
    ) -> Rule:
        doc = await self._get(RULES, rule_id, "No such alert")
        new_channel = channel if channel is not None else doc["channel"]
        new_lead = lead_minutes if lead_minutes is not None else int(doc["lead_minutes"])
        _clean_lead(new_channel, new_lead)
        for other in await self._mine(RULES):
            if other["id"] != rule_id and other["channel"] == new_channel and int(other["lead_minutes"]) == new_lead:
                raise CalendarInvalid("That alert already exists")
        doc.update(channel=new_channel, lead_minutes=new_lead)
        if enabled is not None:
            doc["enabled"] = enabled
        await self._store.put(RULES, doc["key"], doc)
        return Rule.from_doc(doc)

    async def delete_rule(self, rule_id: str) -> None:
        await self._get(RULES, rule_id, "No such alert")
        await self._store.delete(RULES, self._key(rule_id))

    # -- timezone ------------------------------------------------------------------------------
    async def timezone_name(self) -> str:
        return (await self._prefs()).get("timezone", "UTC")

    async def timezone_saved(self) -> bool:
        return "timezone" in await self._prefs()

    async def set_timezone(self, name: str) -> None:
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise CalendarInvalid("Unknown time zone") from None
        await self._set_prefs(timezone=name)

    async def zone(self) -> ZoneInfo:
        try:
            return ZoneInfo(await self.timezone_name())
        except (ZoneInfoNotFoundError, ValueError, OSError):
            return ZoneInfo("UTC")

    # -- push subscriptions --------------------------------------------------------------------
    async def push_subscriptions(self) -> list[PushSubscription]:
        return [PushSubscription(d["key"], d["endpoint"], d["p256dh"], d["auth"]) for d in await self._mine(PUSH)]

    async def add_push(self, endpoint: str, p256dh: str, auth: str) -> None:
        if not endpoint.startswith("https://") or len(endpoint) > 1000 or not p256dh or not auth:
            raise CalendarInvalid("That push subscription is not valid")
        key = self._key(_digest(endpoint, 32))
        if len(await self._mine(PUSH)) >= MAX_PUSH and await self._store.get(PUSH, key) is None:
            raise CalendarLimit(f"At most {MAX_PUSH} browsers can receive push alerts")
        doc = {"key": key, "owner": self._owner, "endpoint": endpoint, "p256dh": p256dh, "auth": auth, "created_at": _now()}
        await self._store.put(PUSH, key, doc)

    async def remove_push(self, endpoint: str) -> None:
        await self._store.delete(PUSH, self._key(_digest(endpoint, 32)))

    async def remove_push_key(self, key: str) -> None:
        if key.startswith(self._owner + ":"):
            await self._store.delete(PUSH, key)

    # -- alerts --------------------------------------------------------------------------------
    async def create_alert(self, rule: Rule, event: CalendarEvent) -> StoredAlert | None:
        """None when this rule already alerted for this event (create-if-absent is the lock)."""
        alert_id = f"{rule.id}-{_digest(event.key, 24)}"
        doc = {
            "key": self._key(alert_id), "owner": self._owner, "id": alert_id, "rule_id": rule.id,
            "title": event.title[:200], "start_utc": event.start.isoformat(), "channel": rule.channel,
            "status": "sent", "state": "new" if rule.channel == "inapp" else "done", "created_at": _now(),
        }
        return StoredAlert.from_doc(doc) if await self._store.create(ALERTS, doc["key"], doc) else None

    async def set_alert_status(self, alert: StoredAlert, status: str) -> None:
        doc = await self._store.get(ALERTS, self._key(alert.id))
        if doc is not None:
            doc["status"] = status
            await self._store.put(ALERTS, doc["key"], doc)

    async def unseen_alerts(self) -> list[StoredAlert]:
        alerts = [StoredAlert.from_doc(d) for d in await self._mine(ALERTS)]
        return sorted((a for a in alerts if a.state == "new"), key=lambda a: a.created_at)

    async def mark_seen(self, alert_id: str) -> None:
        doc = await self._get(ALERTS, alert_id, "No such alert")
        doc["state"] = "seen"
        await self._store.put(ALERTS, doc["key"], doc)

    async def prune_alerts(self, now: datetime) -> int:
        cutoff = (now - ALERT_KEEP).replace(tzinfo=None).isoformat(timespec="seconds")
        removed = 0
        for doc in await self._mine(ALERTS):
            if doc["created_at"] < cutoff:
                removed += await self._store.delete(ALERTS, doc["key"])
        return removed


async def owners_with_rules(store: DocumentStore) -> set[str]:
    """Accounts that have at least one enabled alarm rule (what the scheduler walks)."""
    owners: set[str] = set()
    offset = 0
    while True:
        page = await store.query(RULES, None, limit=PAGE, offset=offset)
        owners.update(d["owner"] for d in page if d.get("enabled") is not False)
        if len(page) < PAGE:
            return owners
        offset += PAGE


async def purge_owner(store: DocumentStore, owner_uid: str) -> int:
    """Delete everything one account kept (used when the account is deleted). Returns the count."""
    removed = 0
    for collection in COLLECTIONS:
        for _ in range(50):
            docs = await store.query(collection, {"owner": owner_uid}, limit=PAGE)
            if not docs:
                break
            for doc in docs:
                removed += await store.delete(collection, doc["key"])
    return removed
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_store.py -q`
Expected: PASS (11 passed). If `owners_with_rules` is passed `None` filters and `FakeDbGateway.query` rejects it, the fake accepts `filters=None` (it does: `(filters or {})`).

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_api/src/services/calendar_store.py apps/Ember/ember_api/tests/test_calendar_store.py
git commit -m "feat(calendar): store feeds, alarm rules, push subscriptions and alerts in db_gateway"
```

---

### Task 5: Feed cache and event source

**Files:**
- Create: `apps/Ember/ember_api/src/services/calendar_events.py`
- Test: `apps/Ember/ember_api/tests/test_calendar_events.py`

**Interfaces:**
- Consumes: `CalendarStore`, `Feed` (Task 4), `CalendarFetcher`, `FetchResult`, `FeedError` (Task 3), `expand`, `merge`, `CalendarEvent` (Task 2).
- Produces: `FeedCache(fetcher, refresh: timedelta, clock: Callable[[], datetime] = utc_now)` with `async body(cal: CalendarStore, feed: Feed) -> bytes` and `forget(owner: str, feed_id: str)`; `EventResult(events: list[CalendarEvent], errors: list[tuple[str, str]])`; `EventSource(cache: FeedCache)` with `async events(cal: CalendarStore, start: datetime, end: datetime) -> EventResult` and `forget(owner, feed_id)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_calendar_events.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_events.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

Create `src/services/calendar_events.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_events.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_api/src/services/calendar_events.py apps/Ember/ember_api/tests/test_calendar_events.py
git commit -m "feat(calendar): cache feed bodies and build merged event lists"
```

---

### Task 6: VAPID keys

**Files:**
- Create: `apps/Ember/ember_api/src/services/vapid.py`
- Test: `apps/Ember/ember_api/tests/test_vapid.py`

**Interfaces:**
- Produces: `VapidKeys(private: str, public: str)` (both url-safe base64 without padding; `private` is the 32-byte raw key, `public` is the uncompressed P-256 point); `ensure_vapid_keys(env_path: Path) -> VapidKeys` (reads `EMBER_VAPID_PRIVATE_KEY` / `EMBER_VAPID_PUBLIC_KEY` from `.env`, generating and appending them when either is missing).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vapid.py`:

```python
from __future__ import annotations

from pathlib import Path

from py_vapid import Vapid

from src.services.vapid import ensure_vapid_keys


def test_keys_are_generated_once_and_persisted(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("OTHER=1", encoding="utf-8")
    first = ensure_vapid_keys(env)
    text = env.read_text(encoding="utf-8")
    assert "OTHER=1\n" in text and f"EMBER_VAPID_PRIVATE_KEY={first.private}" in text
    assert ensure_vapid_keys(env) == first
    Vapid.from_raw(first.private.encode())  # the private half is loadable by pywebpush


def test_a_half_written_pair_is_replaced(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EMBER_VAPID_PRIVATE_KEY=\nEMBER_VAPID_PUBLIC_KEY=old\n", encoding="utf-8")
    keys = ensure_vapid_keys(env)
    text = env.read_text(encoding="utf-8")
    assert text.count("EMBER_VAPID_PRIVATE_KEY=") == 1 and "old" not in text and keys.public in text
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_vapid.py -q`
Expected: FAIL (`ModuleNotFoundError: src.services.vapid`).

- [ ] **Step 3: Implement**

Create `src/services/vapid.py`:

```python
"""The VAPID key pair that identifies ember to browsers' push services, kept in `.env`.

Losing it only means every browser must subscribe to push again; nothing else depends on it.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid

from src.utils.config_loader import load_env_secrets

PRIVATE_NAME = "EMBER_VAPID_PRIVATE_KEY"
PUBLIC_NAME = "EMBER_VAPID_PUBLIC_KEY"


@dataclass(frozen=True)
class VapidKeys:
    private: str
    public: str


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _set(env_path: Path, name: str, value: str) -> None:
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    line = re.compile(rf"(?m)^{name}=.*$")
    if line.search(text):
        text = line.sub(lambda _m: f"{name}={value}", text, count=1)
    else:
        text = f"{text}{'' if not text or text.endswith(chr(10)) else chr(10)}{name}={value}\n"
    env_path.write_text(text, encoding="utf-8")


def ensure_vapid_keys(env_path: Path) -> VapidKeys:
    env = load_env_secrets(env_path)
    private, public = env.get(PRIVATE_NAME, "").strip(), env.get(PUBLIC_NAME, "").strip()
    if private and public:
        return VapidKeys(private, public)
    vapid = Vapid()
    vapid.generate_keys()
    private = _b64(vapid.private_key.private_numbers().private_value.to_bytes(32, "big"))
    public = _b64(vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    _set(env_path, PRIVATE_NAME, private)
    _set(env_path, PUBLIC_NAME, public)
    return VapidKeys(private, public)
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_vapid.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_api/src/services/vapid.py apps/Ember/ember_api/tests/test_vapid.py
git commit -m "feat(calendar): generate and keep the VAPID key pair in .env"
```

---

### Task 7: Alert channels (in-app, email, push)

**Files:**
- Create: `apps/Ember/ember_api/src/services/alert_channels.py`
- Create: `apps/Ember/ember_api/src/services/email_templates/calendar_alert.txt`
- Modify: `apps/Ember/ember_api/src/services/email_service.py`
- Modify: `apps/Ember/ember_api/tests/conftest.py` (`FakeEmailSender`)
- Test: `apps/Ember/ember_api/tests/test_alert_channels.py`

**Interfaces:**
- Consumes: `CalendarStore` (Task 4), `EmailSender` (existing), `VapidKeys` (Task 6).
- Produces: `AlertMessage(title: str, start: datetime, lead_minutes: int, sources: tuple[str, ...])`; `Recipient(uid: str, email: str)`; `ChannelError(Exception)`; `Channel` protocol (`async send(message: AlertMessage, recipient: Recipient, cal: CalendarStore) -> None`); `InAppChannel()`, `EmailChannel(sender: EmailSender)`, `PushChannel(private_key: str, contact: str, sender: PushSender = send_web_push)`; `EmailSender.send_notification(to: str, subject: str, body: str) -> None` (added to the protocol, `McpEmailSender` and `FakeEmailSender`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_alert_channels.py`:

```python
from __future__ import annotations

import asyncio
import json
import types
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from pywebpush import WebPushException

from src.config import CalendarSettings
from src.services.alert_channels import (
    AlertMessage, ChannelError, EmailChannel, InAppChannel, PushChannel, Recipient,
)
from src.services.calendar_store import CalendarStore
from src.services.secret_box import SecretBox
from src.services.vapid import ensure_vapid_keys
from tests.conftest import FakeDbGateway, FakeEmailSender

WHO = Recipient("u1", "ada@example.com")
MESSAGE = AlertMessage("Standup\nBCC: x", datetime(2026, 10, 26, 13, tzinfo=timezone.utc), 15, ("Work",))


def store() -> CalendarStore:
    return CalendarStore(FakeDbGateway(), "u1", SecretBox(Fernet.generate_key().decode("ascii")), CalendarSettings())


def test_in_app_sends_nothing() -> None:
    assert asyncio.run(InAppChannel().send(MESSAGE, WHO, store())) is None


def test_email_goes_to_the_recipient_with_a_single_line_subject() -> None:
    sender = FakeEmailSender()
    cal = store()
    asyncio.run(cal.set_timezone("America/New_York"))
    asyncio.run(EmailChannel(sender).send(MESSAGE, WHO, cal))
    (kind, to, text), = sender.sent
    assert (kind, to) == ("notification", "ada@example.com")
    subject, body = text.split("\n\n", 1) if "\n\n" in text else text.split("\n", 1)
    assert subject == "Starting in 15 min: Standup BCC: x" and "\n" not in subject
    assert "09:00" in body and "America/New_York" in body and "Work" in body


def test_email_failure_propagates_so_the_scheduler_can_mark_it() -> None:
    sender = FakeEmailSender(fail=True)
    with pytest.raises(Exception):
        asyncio.run(EmailChannel(sender).send(MESSAGE, WHO, store()))


def push_channel(sent: list, raises: Exception | None = None) -> PushChannel:
    keys = ensure_vapid_keys(_env())

    def sender(subscription, payload, vapid, claims):
        sent.append((subscription["endpoint"], json.loads(payload), claims))
        if raises:
            raise raises

    return PushChannel(keys.private, "mailto:admin@example.com", sender)


def _env():
    import tempfile
    from pathlib import Path
    return Path(tempfile.mkdtemp()) / ".env"


def test_push_reaches_every_subscription() -> None:
    cal, sent = store(), []
    asyncio.run(cal.add_push("https://push.example/a", "k", "s"))
    asyncio.run(cal.add_push("https://push.example/b", "k", "s"))
    asyncio.run(push_channel(sent).send(MESSAGE, WHO, cal))
    assert sorted(e for e, _, _ in sent) == ["https://push.example/a", "https://push.example/b"]
    _, payload, claims = sent[0]
    assert payload == {"title": "Standup BCC: x", "body": "Starts in 15 min", "url": "/calendar"}
    assert claims == {"sub": "mailto:admin@example.com"}


def test_push_without_a_subscription_is_a_channel_error() -> None:
    with pytest.raises(ChannelError):
        asyncio.run(push_channel([]).send(MESSAGE, WHO, store()))


def test_a_gone_subscription_is_removed() -> None:
    cal, sent = store(), []
    asyncio.run(cal.add_push("https://push.example/a", "k", "s"))
    gone = WebPushException("gone", response=types.SimpleNamespace(status_code=410))
    with pytest.raises(ChannelError):
        asyncio.run(push_channel(sent, gone).send(MESSAGE, WHO, cal))
    assert asyncio.run(cal.push_subscriptions()) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_alert_channels.py -q`
Expected: FAIL (`ModuleNotFoundError: src.services.alert_channels`).

- [ ] **Step 3: Extend the email sender**

In `src/services/email_service.py` add to the `EmailSender` protocol:

```python
    async def send_notification(self, to: str, subject: str, body: str) -> None: ...
```

and to `McpEmailSender` (after `send_email_verification`):

```python
    async def send_notification(self, to: str, subject: str, body: str) -> None:
        await self._send(to, subject, body)
```

In `tests/conftest.py` add to `FakeEmailSender` (after `send_email_verification`):

```python
    async def send_notification(self, to: str, subject: str, body: str) -> None:
        self._record("notification", to, f"{subject}\n\n{body}")
```

Create `src/services/email_templates/calendar_alert.txt`:

```
Your event "$title" starts in $lead minutes.

When: $when
Calendar: $sources

You get this because you set an alert in Ember's Calendar. Change it there at any time.
```

- [ ] **Step 4: Implement the channels**

Create `src/services/alert_channels.py`:

```python
"""The ways an alert can reach an account. One class per channel; a new channel is a new class."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from src.services.calendar_store import CalendarStore
from src.services.email_service import EmailSender, render_template


@dataclass(frozen=True)
class AlertMessage:
    title: str
    start: datetime  # aware
    lead_minutes: int
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Recipient:
    uid: str
    email: str


class ChannelError(Exception):
    """The alert could not be delivered. The message is safe to log."""


class Channel(Protocol):
    async def send(self, message: AlertMessage, recipient: Recipient, cal: CalendarStore) -> None: ...


def _one_line(text: str) -> str:
    return " ".join(text.split())


class InAppChannel:
    """The stored alert is the notification: the open page polls for it. Nothing to push."""

    async def send(self, message: AlertMessage, recipient: Recipient, cal: CalendarStore) -> None:
        return None


class EmailChannel:
    def __init__(self, sender: EmailSender) -> None:
        self._sender = sender

    async def send(self, message: AlertMessage, recipient: Recipient, cal: CalendarStore) -> None:
        zone = await cal.zone()
        title = _one_line(message.title)
        body = render_template(
            "calendar_alert",
            title=title,
            lead=str(message.lead_minutes),
            when=f"{message.start.astimezone(zone):%a %d %b %H:%M} ({zone.key})",
            sources=", ".join(message.sources) or "your calendar",
        )
        await self._sender.send_notification(recipient.email, f"Starting in {message.lead_minutes} min: {title}"[:150], body)


PushSender = Callable[[dict[str, Any], str, Vapid, dict[str, str]], None]


def send_web_push(subscription: dict[str, Any], payload: str, vapid: Vapid, claims: dict[str, str]) -> None:
    webpush(subscription_info=subscription, data=payload, vapid_private_key=vapid, vapid_claims=claims, ttl=600)


class PushChannel:
    def __init__(self, private_key: str, contact: str, sender: PushSender = send_web_push) -> None:
        self._vapid = Vapid.from_raw(private_key.encode("ascii"))
        self._contact = contact
        self._sender = sender

    async def send(self, message: AlertMessage, recipient: Recipient, cal: CalendarStore) -> None:
        subscriptions = await cal.push_subscriptions()
        if not subscriptions:
            raise ChannelError("No browser is subscribed to push")
        payload = json.dumps({
            "title": _one_line(message.title)[:150],
            "body": f"Starts in {message.lead_minutes} min",
            "url": "/calendar",
        })
        delivered = 0
        for subscription in subscriptions:
            try:
                # pywebpush blocks, and the claims dict is mutated per call, so each call gets its own.
                await asyncio.to_thread(self._sender, subscription.info(), payload, self._vapid, {"sub": self._contact})
                delivered += 1
            except WebPushException as error:
                if getattr(error.response, "status_code", None) in (404, 410):
                    await cal.remove_push_key(subscription.key)
            except Exception:  # one broken browser must not block the others
                continue
        if not delivered:
            raise ChannelError("Push could not be delivered")
```

- [ ] **Step 5: Run to verify pass**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_alert_channels.py tests/test_email_service.py tests/test_registration.py -q`
Expected: PASS. Adjust the email-test split line only if the subject/body separator differs from `"\n\n"` (the fake joins them with a blank line).

- [ ] **Step 6: Commit**

```bash
git add apps/Ember/ember_api/src/services/alert_channels.py apps/Ember/ember_api/src/services/email_templates/calendar_alert.txt apps/Ember/ember_api/src/services/email_service.py apps/Ember/ember_api/tests/conftest.py apps/Ember/ember_api/tests/test_alert_channels.py
git commit -m "feat(calendar): in-app, email and web push alert channels"
```

---

### Task 8: Alert scheduler

**Files:**
- Create: `apps/Ember/ember_api/src/services/alert_scheduler.py`
- Test: `apps/Ember/ember_api/tests/test_alert_scheduler.py`

**Interfaces:**
- Consumes: `CalendarStore`, `owners_with_rules`, `StoredAlert`, `Rule` (Task 4); `EventSource`, `EventResult` (Task 5); `Channel`, `AlertMessage`, `Recipient` (Task 7); `CalendarSettings` (Task 1).
- Produces: `is_due(start: datetime, lead_minutes: int, now: datetime, grace_minutes: int) -> bool`; `AlertScheduler(*, store: DocumentStore, box: SecretBox, events: EventSource, channels: Mapping[str, Channel], settings: CalendarSettings, lookup: Callable[[str], Awaitable[Recipient | None]], switches: Callable[[], Awaitable[dict[str, bool]]], on_error: Callable[[str], Awaitable[None]] | None = None, clock=utc_now, sleep=asyncio.sleep)` with `start()`, `async stop()`, `async tick(now: datetime)`. `switches()` returns the `app_settings` booleans (keys `calendar_<channel>`); `lookup(uid)` returns the recipient only for an active, permitted account.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_alert_scheduler.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_alert_scheduler.py -q`
Expected: FAIL (`ModuleNotFoundError: src.services.alert_scheduler`).

- [ ] **Step 3: Implement**

Create `src/services/alert_scheduler.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_alert_scheduler.py -q`
Expected: PASS (8 passed). Note: `_report` dedupes by message; `test_a_failing_channel...` expects exactly one entry.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_api/src/services/alert_scheduler.py apps/Ember/ember_api/tests/test_alert_scheduler.py
git commit -m "feat(calendar): scheduler that fires alarm rules once per event"
```

---

### Task 9: Runtime wiring, routes, account purge, config warning

**Files:**
- Create: `apps/Ember/ember_api/src/services/calendar_runtime.py`
- Create: `apps/Ember/ember_api/src/routes/calendar.py`
- Modify: `apps/Ember/ember_api/src/app.py`
- Modify: `apps/Ember/ember_api/src/routes/admin.py` (account delete, imports)
- Modify: `apps/Ember/ember_api/src/services/config_validation.py` (`_check_deployment`)
- Modify: `apps/Ember/ember_api/README.md`
- Test: `apps/Ember/ember_api/tests/test_calendar_routes.py`

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces: `CalendarRuntime(events: EventSource, scheduler: AlertScheduler | None, vapid_public: str, client: httpx.AsyncClient)` mutable dataclass with `async close()`; `build_calendar_runtime(*, settings: Settings, database: Database, store: DocumentStore, box: SecretBox, email_sender: EmailSender, log_writer: LogWriter) -> CalendarRuntime`; `app.state.calendar` is a `CalendarRuntime` or `None` (when `calendar.enabled` is false); routes under `/api/calendar` (below).

Route contract (all need `calendar.use`; 404 "Calendar is switched off" when `app.state.calendar is None`):

| Method + path | Body / query | Reply |
| --- | --- | --- |
| `GET /feeds` | | `[{id,name,color,enabled,last_fetch_at,last_error}]` |
| `POST /feeds` | `{name,url,color}` | 201 feed |
| `PATCH /feeds/{id}` | any of `name,color,enabled,url` | feed |
| `DELETE /feeds/{id}` | | 204 |
| `GET /events?from=&to=` | ISO datetimes, range ≤ 62 days | `{events:[{uid,title,start,end,all_day,location,description,sources:[{name,color}]}], errors:[{feed,message}]}` |
| `GET /alarms` | | `[{id,channel,lead_minutes,enabled}]` (seeds the default rule) |
| `POST /alarms` | `{channel,lead_minutes}` | 201 rule |
| `PATCH /alarms/{id}` | any of `channel,lead_minutes,enabled` | rule |
| `DELETE /alarms/{id}` | | 204 |
| `GET /prefs` | | `{timezone,saved}` |
| `PUT /prefs` | `{timezone}` | `{timezone,saved}` |
| `GET /push/key` | | `{key}` |
| `POST /push/subscribe` | `{endpoint,keys:{p256dh,auth}}` | 204 |
| `POST /push/unsubscribe` | `{endpoint}` | 204 |
| `GET /alerts?unseen=1` | | `[{id,title,start_utc,channel,created_at}]` (in-app inbox only) |
| `POST /alerts/{id}/seen` | | 204 |

- [ ] **Step 1: Write the failing route tests**

Create `tests/test_calendar_routes.py`:

```python
"""/api/calendar: feeds, events, alarm rules, prefs, push and the alert inbox."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from src.models import Account
from src.services.calendar_events import EventSource, FeedCache
from src.services.calendar_expander import CalendarEvent
from src.services.calendar_fetcher import FeedError, FetchResult
from src.services.calendar_store import CalendarStore
from tests.conftest import FakeDbGateway
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

URL = "/api/calendar"
FEED_URL = "https://outlook.office365.com/owa/calendar/abc/private/reachcalendar.ics"
ICS = (
    "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//t//EN\nBEGIN:VEVENT\nUID:e1\n"
    "DTSTART:20261026T090000Z\nDTEND:20261026T100000Z\nSUMMARY:Standup\nLOCATION:Room 1\nEND:VEVENT\nEND:VCALENDAR\n"
).encode()


class FakeFetcher:
    def __init__(self, result) -> None:
        self.result, self.urls = result, []

    async def fetch(self, url, etag=None):
        self.urls.append(url)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def feed_source(client: TestClient, result) -> FakeFetcher:
    fetcher = FakeFetcher(result)
    client.app.state.calendar.events = EventSource(FeedCache(fetcher, timedelta(minutes=10)))
    return fetcher


def add_feed(client: TestClient, name: str = "Work", url: str = FEED_URL, color: str = "#2563eb"):
    return client.post(f"{URL}/feeds", json={"name": name, "url": url, "color": color})


def test_every_route_needs_login_and_the_permission(client: TestClient, email) -> None:
    assert client.get(f"{URL}/feeds").status_code == 401
    make_member(client, email)
    login(client, "alice")
    for method, path in (("get", "/feeds"), ("get", "/alarms"), ("get", "/events?from=2026-10-26T00:00:00Z&to=2026-10-27T00:00:00Z")):
        assert getattr(client, method)(URL + path).status_code == 403


def test_add_list_update_and_delete_a_feed_without_ever_returning_the_link(client: TestClient) -> None:
    as_admin(client)
    created = add_feed(client, url="webcal://outlook.office365.com/x.ics")
    assert created.status_code == 201
    feed = created.json()
    assert set(feed) == {"id", "name", "color", "enabled", "last_fetch_at", "last_error"}
    listed = client.get(f"{URL}/feeds")
    patched = client.patch(f"{URL}/feeds/{feed['id']}", json={"name": "Job", "enabled": False})
    for response in (created, listed, patched):
        assert "outlook.office365.com" not in response.text
    assert patched.json()["name"] == "Job" and patched.json()["enabled"] is False
    assert client.delete(f"{URL}/feeds/{feed['id']}").status_code == 204
    assert client.get(f"{URL}/feeds").json() == []


def test_bad_feeds_are_refused_with_a_message(client: TestClient) -> None:
    as_admin(client)
    assert add_feed(client, url="http://x.com/a.ics").status_code == 400
    assert add_feed(client, color="blue").status_code == 400
    assert client.patch(f"{URL}/feeds/nope", json={"name": "x"}).status_code == 404
    assert client.patch(f"{URL}/feeds/abc", json={}).status_code == 422


def test_events_are_merged_with_feed_colors_and_problems_are_listed(client: TestClient) -> None:
    as_admin(client)
    add_feed(client)
    feed_source(client, FetchResult(ICS, None))
    reply = client.get(f"{URL}/events", params={"from": "2026-10-26T00:00:00Z", "to": "2026-10-27T00:00:00Z"}).json()
    assert reply["errors"] == []
    (event,) = reply["events"]
    assert event["title"] == "Standup" and event["location"] == "Room 1" and event["all_day"] is False
    assert event["sources"] == [{"name": "Work", "color": "#2563eb"}]
    feed_source(client, FeedError("The feed answered HTTP 500"))
    broken = client.get(f"{URL}/events", params={"from": "2026-10-26T00:00:00Z", "to": "2026-10-27T00:00:00Z"}).json()
    assert broken["events"] == [] and broken["errors"] == [{"feed": "Work", "message": "The feed answered HTTP 500"}]


def test_event_range_is_validated(client: TestClient) -> None:
    as_admin(client)
    for query in ({"from": "2026-10-27T00:00:00Z", "to": "2026-10-26T00:00:00Z"},
                  {"from": "2026-01-01T00:00:00Z", "to": "2026-12-31T00:00:00Z"}, {"from": "x", "to": "y"}):
        assert client.get(f"{URL}/events", params=query).status_code == 422


def test_alarm_rules_start_with_the_default_and_can_be_managed(client: TestClient) -> None:
    as_admin(client)
    (default,) = client.get(f"{URL}/alarms").json()
    assert (default["channel"], default["lead_minutes"], default["enabled"]) == ("inapp", 15, True)
    created = client.post(f"{URL}/alarms", json={"channel": "email", "lead_minutes": 30})
    assert created.status_code == 201
    assert client.post(f"{URL}/alarms", json={"channel": "sms", "lead_minutes": 30}).status_code == 400
    assert client.post(f"{URL}/alarms", json={"channel": "email", "lead_minutes": 30}).status_code == 400
    patched = client.patch(f"{URL}/alarms/{created.json()['id']}", json={"lead_minutes": 60, "enabled": False})
    assert patched.json()["lead_minutes"] == 60 and patched.json()["enabled"] is False
    assert client.delete(f"{URL}/alarms/{default['id']}").status_code == 204
    assert [r["channel"] for r in client.get(f"{URL}/alarms").json()] == ["email"]


def test_prefs_timezone(client: TestClient) -> None:
    as_admin(client)
    assert client.get(f"{URL}/prefs").json() == {"timezone": "UTC", "saved": False}
    assert client.put(f"{URL}/prefs", json={"timezone": "Europe/Madrid"}).json() == {"timezone": "Europe/Madrid", "saved": True}
    assert client.put(f"{URL}/prefs", json={"timezone": "Mars/Base"}).status_code == 400


def test_push_key_subscribe_and_unsubscribe(client: TestClient) -> None:
    as_admin(client)
    assert len(client.get(f"{URL}/push/key").json()["key"]) > 60
    body = {"endpoint": "https://push.example/a", "keys": {"p256dh": "k", "auth": "s"}}
    assert client.post(f"{URL}/push/subscribe", json=body).status_code == 204
    assert client.post(f"{URL}/push/subscribe", json={**body, "endpoint": "http://push.example/a"}).status_code == 400
    assert client.post(f"{URL}/push/unsubscribe", json={"endpoint": body["endpoint"]}).status_code == 204


def test_alert_inbox_lists_in_app_alerts_and_marks_them_seen(client: TestClient, db_gateway: FakeDbGateway) -> None:
    as_admin(client)
    client.get(f"{URL}/alarms")  # seeds the default rule, which creates the account's documents
    owner = next(key.split(":")[0] for (collection, key) in db_gateway.records if collection == "calendar_rules")
    cal = CalendarStore(db_gateway, owner, client.app.state.secret_box, client.app.state.settings.calendar)
    (rule,) = asyncio.run(cal.rules())
    start = datetime(2026, 10, 26, 10, tzinfo=timezone.utc)
    asyncio.run(cal.create_alert(rule, CalendarEvent("e1", "Standup", start, start + timedelta(hours=1), False, "", "")))
    (alert,) = client.get(f"{URL}/alerts", params={"unseen": 1}).json()
    assert alert["title"] == "Standup" and alert["channel"] == "inapp"
    assert client.post(f"{URL}/alerts/{alert['id']}/seen", json={}).status_code == 204
    assert client.get(f"{URL}/alerts", params={"unseen": 1}).json() == []
    assert client.post(f"{URL}/alerts/nope/seen", json={}).status_code == 404


def test_deleting_an_account_purges_its_calendar(client: TestClient, email, db_gateway: FakeDbGateway) -> None:
    account_id = make_member(client, email, "carol")
    as_admin(client)

    async def uid_of(username: str) -> str:
        async with client.app.state.database.sessions() as session:
            return await session.scalar(select(Account.uid).where(Account.username == username))

    uid = client.portal.call(uid_of, "carol")  # runs on the app's own event loop
    for collection in ("calendar_feeds", "calendar_rules", "calendar_prefs"):
        db_gateway.records[(collection, f"{uid}:x")] = {"key": f"{uid}:x", "owner": uid}
    db_gateway.records[("calendar_feeds", "other:x")] = {"key": "other:x", "owner": "other"}
    assert client.delete(f"/api/admin/accounts/{account_id}").status_code == 204
    assert [k for (c, k) in db_gateway.records if c.startswith("calendar_")] == ["other:x"]
```

Before running, read `tests/test_admin.py::make_member` and `test_delete_account`: the last test assumes `make_member` returns the new account's id, creates `carol` and leaves the client free to call `as_admin` afterwards. Adjust only that call pattern if it differs. POST requests in these tests pass `json={}` because `JsonOnlyMiddleware` refuses a POST without a JSON content type; `client.portal.call(...)` runs a coroutine on the app's own event loop (the client from `client_factory` is entered, so the portal exists).

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_routes.py -q`
Expected: FAIL (404 on `/api/calendar/...`, or `AttributeError: state has no attribute 'calendar'`).

- [ ] **Step 3: Runtime wiring**

Create `src/services/calendar_runtime.py`:

```python
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
```

- [ ] **Step 4: Routes**

Create `src/routes/calendar.py`:

```python
"""/api/calendar: the logged-in account's read-only schedule (ICS links) and its alerts.

Private to the account. A feed's link is accepted on create and update and never sent back.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, Field, model_validator

from src.config import Settings
from src.deps import get_db_gateway, get_secret_box, get_settings, require_permission
from src.models import Account
from src.services.calendar_runtime import CalendarRuntime
from src.services.calendar_store import CalendarStore, Feed, Rule, StoredAlert
from src.services.db_gateway import DocumentStore
from src.services.permissions import CALENDAR_USE
from src.services.secret_box import SecretBox

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
require_calendar = require_permission(CALENDAR_USE)

MAX_RANGE = timedelta(days=62)
ItemId = Annotated[str, Path(pattern=r"^[a-z0-9-]{1,80}$")]


def get_runtime(request: Request) -> CalendarRuntime:
    runtime: CalendarRuntime | None = request.app.state.calendar
    if runtime is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Calendar is switched off")
    return runtime


def get_calendar(
    account: Account = Depends(require_calendar),
    _runtime: CalendarRuntime = Depends(get_runtime),
    store: DocumentStore = Depends(get_db_gateway),
    box: SecretBox = Depends(get_secret_box),
    settings: Settings = Depends(get_settings),
) -> CalendarStore:
    return CalendarStore(store, account.uid, box, settings.calendar)


class FeedOut(BaseModel):
    id: str
    name: str
    color: str
    enabled: bool
    last_fetch_at: str | None
    last_error: str | None

    @classmethod
    def of(cls, feed: Feed) -> FeedOut:
        return cls(id=feed.id, name=feed.name, color=feed.color, enabled=feed.enabled,
                   last_fetch_at=feed.last_fetch_at, last_error=feed.last_error)


class FeedIn(BaseModel):
    name: str = Field(max_length=200)
    url: str = Field(max_length=2000)
    color: str = Field(max_length=7)


class FeedPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, max_length=7)
    enabled: bool | None = None

    @model_validator(mode="after")
    def something_to_change(self) -> FeedPatch:
        if not self.model_fields_set:
            raise ValueError("send something to change")
        return self


@router.get("/feeds")
async def list_feeds(cal: CalendarStore = Depends(get_calendar)) -> list[FeedOut]:
    return [FeedOut.of(f) for f in await cal.feeds()]


@router.post("/feeds", status_code=status.HTTP_201_CREATED)
async def add_feed(body: FeedIn, cal: CalendarStore = Depends(get_calendar)) -> FeedOut:
    return FeedOut.of(await cal.add_feed(body.name, body.url, body.color))


@router.patch("/feeds/{feed_id}")
async def update_feed(
    feed_id: ItemId, body: FeedPatch, account: Account = Depends(require_calendar),
    cal: CalendarStore = Depends(get_calendar), runtime: CalendarRuntime = Depends(get_runtime),
) -> FeedOut:
    feed = await cal.update_feed(feed_id, **body.model_dump(exclude_unset=True))
    runtime.events.forget(account.uid, feed_id)
    return FeedOut.of(feed)


@router.delete("/feeds/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feed(
    feed_id: ItemId, account: Account = Depends(require_calendar),
    cal: CalendarStore = Depends(get_calendar), runtime: CalendarRuntime = Depends(get_runtime),
) -> Response:
    await cal.delete_feed(feed_id)
    runtime.events.forget(account.uid, feed_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class SourceOut(BaseModel):
    name: str
    color: str


class EventOut(BaseModel):
    uid: str
    title: str
    start: datetime
    end: datetime
    all_day: bool
    location: str
    description: str
    sources: list[SourceOut]


class FeedProblem(BaseModel):
    feed: str
    message: str


class EventsOut(BaseModel):
    events: list[EventOut]
    errors: list[FeedProblem]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.get("/events")
async def list_events(
    start: Annotated[datetime, Query(alias="from")], end: Annotated[datetime, Query(alias="to")],
    cal: CalendarStore = Depends(get_calendar), runtime: CalendarRuntime = Depends(get_runtime),
) -> EventsOut:
    start, end = _aware(start), _aware(end)
    if end <= start or end - start > MAX_RANGE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ask for at most 62 days, with the end after the start")
    result = await runtime.events.events(cal, start, end)
    colors = {f.name: f.color for f in await cal.feeds()}
    return EventsOut(
        events=[EventOut(
            uid=e.uid, title=e.title, start=e.start, end=e.end, all_day=e.all_day, location=e.location,
            description=e.description, sources=[SourceOut(name=n, color=colors.get(n, "#808080")) for n in e.sources],
        ) for e in result.events],
        errors=[FeedProblem(feed=n, message=m) for n, m in result.errors],
    )


class RuleOut(BaseModel):
    id: str
    channel: str
    lead_minutes: int
    enabled: bool

    @classmethod
    def of(cls, rule: Rule) -> RuleOut:
        return cls(id=rule.id, channel=rule.channel, lead_minutes=rule.lead_minutes, enabled=rule.enabled)


class RuleIn(BaseModel):
    channel: str = Field(max_length=16)
    lead_minutes: int


class RulePatch(BaseModel):
    channel: str | None = Field(default=None, max_length=16)
    lead_minutes: int | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def something_to_change(self) -> RulePatch:
        if not self.model_fields_set:
            raise ValueError("send something to change")
        return self


@router.get("/alarms")
async def list_alarms(cal: CalendarStore = Depends(get_calendar)) -> list[RuleOut]:
    return [RuleOut.of(r) for r in await cal.rules()]


@router.post("/alarms", status_code=status.HTTP_201_CREATED)
async def add_alarm(body: RuleIn, cal: CalendarStore = Depends(get_calendar)) -> RuleOut:
    return RuleOut.of(await cal.add_rule(body.channel, body.lead_minutes))


@router.patch("/alarms/{rule_id}")
async def update_alarm(rule_id: ItemId, body: RulePatch, cal: CalendarStore = Depends(get_calendar)) -> RuleOut:
    return RuleOut.of(await cal.update_rule(rule_id, **body.model_dump(exclude_unset=True)))


@router.delete("/alarms/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alarm(rule_id: ItemId, cal: CalendarStore = Depends(get_calendar)) -> Response:
    await cal.delete_rule(rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class PrefsOut(BaseModel):
    timezone: str
    saved: bool


class PrefsIn(BaseModel):
    timezone: str = Field(max_length=64)


async def _prefs(cal: CalendarStore) -> PrefsOut:
    return PrefsOut(timezone=await cal.timezone_name(), saved=await cal.timezone_saved())


@router.get("/prefs")
async def read_prefs(cal: CalendarStore = Depends(get_calendar)) -> PrefsOut:
    return await _prefs(cal)


@router.put("/prefs")
async def save_prefs(body: PrefsIn, cal: CalendarStore = Depends(get_calendar)) -> PrefsOut:
    await cal.set_timezone(body.timezone)
    return await _prefs(cal)


class PushKeys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class PushIn(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: PushKeys


class PushOut(BaseModel):
    endpoint: str = Field(max_length=1000)


@router.get("/push/key")
async def push_key(runtime: CalendarRuntime = Depends(get_runtime), _a: Account = Depends(require_calendar)) -> dict[str, str]:
    return {"key": runtime.vapid_public}


@router.post("/push/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe(body: PushIn, cal: CalendarStore = Depends(get_calendar)) -> Response:
    await cal.add_push(body.endpoint, body.keys.p256dh, body.keys.auth)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/push/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(body: PushOut, cal: CalendarStore = Depends(get_calendar)) -> Response:
    await cal.remove_push(body.endpoint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class AlertOut(BaseModel):
    id: str
    title: str
    start_utc: str
    channel: str
    created_at: str

    @classmethod
    def of(cls, alert: StoredAlert) -> AlertOut:
        return cls(id=alert.id, title=alert.title, start_utc=alert.start_utc, channel=alert.channel, created_at=alert.created_at)


@router.get("/alerts")
async def list_alerts(unseen: bool = False, cal: CalendarStore = Depends(get_calendar)) -> list[AlertOut]:
    """The in-app inbox: alerts that fired for an in-app rule and were not dismissed."""
    return [AlertOut.of(a) for a in await cal.unseen_alerts()]


@router.post("/alerts/{alert_id}/seen", status_code=status.HTTP_204_NO_CONTENT)
async def mark_seen(alert_id: ItemId, cal: CalendarStore = Depends(get_calendar)) -> Response:
    await cal.mark_seen(alert_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 5: Wire the app, account purge, config warning**

In `src/app.py`:
- add imports: `calendar as calendar_routes` to the `from src.routes import (...)` list, `from src.services.calendar_runtime import build_calendar_runtime`, `from src.services.calendar_store import CalendarError`.
- in the lifespan, after `app.state.turns = TurnRegistry(...)` block and before `backups: BackupScheduler | None = None`, add:

```python
        app.state.calendar = (
            build_calendar_runtime(
                settings=settings, database=database, store=app.state.db_gateway, box=secret_box,
                email_sender=app.state.email_sender, log_writer=log_writer,
            )
            if settings.calendar.enabled
            else None
        )
```

- in the `finally:` block, before `if backups is not None:`, add:

```python
            if app.state.calendar is not None:
                await app.state.calendar.close()
```

- after `app.include_router(capability_files.router)` add `app.include_router(calendar_routes.router)`.
- next to the `CapabilityFailure` handler add:

```python
    @app.exception_handler(CalendarError)
    async def calendar_error(_request: Request, error: CalendarError):
        return JSONResponse({"detail": str(error)}, status_code=error.status)
```

In `src/routes/admin.py` add the import `from src.services.calendar_store import purge_owner as purge_calendar` next to the other purge imports and, in `delete_account`, after `await purge_user_extensions(store, uid)` add `await purge_calendar(store, uid)`.

In `src/services/config_validation.py::_check_deployment`, after the `cookie_secure` problem block add:

```python
    if settings.calendar.enabled and not settings.cookie_secure and not _is_local_host(settings.host):
        problems.append(
            (
                "calendar.enabled",
                "is true while ember is not served over HTTPS: browsers refuse web push alerts there. Serve ember over HTTPS and set cookie_secure to true",
            )
        )
```

Add a test to `tests/test_calendar_config.py`:

```python
def test_push_over_plain_http_on_a_reachable_host_is_a_warning(tmp_path) -> None:
    import dataclasses

    from src.services.config_validation import _check_deployment
    from tests.conftest import make_settings

    reachable = dataclasses.replace(make_settings(tmp_path), host="0.0.0.0")
    assert any(key == "calendar.enabled" for key, _ in _check_deployment(reachable))
    assert not any(key == "calendar.enabled" for key, _ in _check_deployment(make_settings(tmp_path)))
```

In `README.md` add a short "Calendar" section after the existing configuration sections: the `calendar` block keys (copy the table from the spec's Static config), the three admin channel switches, `EMBER_VAPID_PRIVATE_KEY`/`EMBER_VAPID_PUBLIC_KEY` in `.env` (generated on first start; deleting them makes every browser subscribe again), and that web push needs HTTPS and the built web app.

- [ ] **Step 6: Run the tests**

Run: `cd apps/Ember/ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest tests/test_calendar_routes.py tests/test_calendar_config.py -q`
Expected: PASS. Then the full suite: `./.venv_ember_api/Scripts/python.exe -m pytest -q` — Expected: all pass (the existing count plus the new tests). Fix any exact-list assertions on routers, permissions or settings.

- [ ] **Step 7: Commit**

```bash
git add apps/Ember/ember_api/src apps/Ember/ember_api/tests apps/Ember/ember_api/README.md
git commit -m "feat(calendar): /api/calendar routes, runtime wiring, account purge"
```

---

### Task 10: ember_web foundations (dependencies, client, event utilities)

**Files:**
- Modify: `apps/Ember/ember_web/package.json` (via npm)
- Create: `apps/Ember/ember_web/src/features/calendar/api/CalendarClient.ts`
- Create: `apps/Ember/ember_web/src/features/calendar/api/CalendarClient.test.ts`
- Create: `apps/Ember/ember_web/src/features/calendar/utils/eventDetails.ts`
- Create: `apps/Ember/ember_web/src/features/calendar/utils/eventDetails.test.ts`
- Create: `apps/Ember/ember_web/src/features/calendar/utils/palette.ts`

**Interfaces:**
- Produces: types `AlarmChannel`, `CalendarFeed`, `CalendarEvent`, `FeedProblem`, `EventsReply`, `AlarmRule`, `CalendarAlert`, `ChannelSwitches`, `Prefs`; `calendarClient` (methods below); `eventDetails.ts` exports `readableUrl(raw): URL | null`, `isTeamsMeeting(url): boolean`, `splitDescription(text): { description: string; footer: string }`, `findTeamsLink(...texts: string[]): string | null`, `linkify(text): TextPart[]` where `TextPart = { text: string } | { href: string; label: string }`; `palette.ts` exports `FEED_COLORS: readonly string[]` and `nextFeedColor(used: readonly string[]): string`.

- [ ] **Step 1: Install FullCalendar**

Run: `cd apps/Ember/ember_web && npm install @fullcalendar/core @fullcalendar/vue3 @fullcalendar/daygrid @fullcalendar/timegrid`
Expected: four packages added to `dependencies`.

- [ ] **Step 2: Write the failing tests**

Create `src/features/calendar/api/CalendarClient.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "../../../api/http";
import { calendarClient } from "./CalendarClient";

vi.mock("../../../api/http", () => ({ apiRequest: vi.fn() }));
const request = vi.mocked(apiRequest);

beforeEach(() => vi.clearAllMocks());

describe("calendarClient", () => {
  it("manages feeds", async () => {
    request.mockResolvedValue([]);
    await calendarClient.feeds();
    expect(request).toHaveBeenLastCalledWith("GET", "/api/calendar/feeds");
    await calendarClient.addFeed({ name: "Work", url: "webcal://x/a.ics", color: "#2563eb" });
    expect(request).toHaveBeenLastCalledWith("POST", "/api/calendar/feeds", { name: "Work", url: "webcal://x/a.ics", color: "#2563eb" });
    await calendarClient.updateFeed("f1", { enabled: false });
    expect(request).toHaveBeenLastCalledWith("PATCH", "/api/calendar/feeds/f1", { enabled: false });
    await calendarClient.removeFeed("f1");
    expect(request).toHaveBeenLastCalledWith("DELETE", "/api/calendar/feeds/f1");
  });

  it("asks for events in a range as ISO times", async () => {
    request.mockResolvedValue({ events: [], errors: [] });
    await calendarClient.events(new Date("2026-10-26T00:00:00Z"), new Date("2026-11-02T00:00:00Z"));
    expect(request).toHaveBeenLastCalledWith(
      "GET",
      "/api/calendar/events?from=2026-10-26T00%3A00%3A00.000Z&to=2026-11-02T00%3A00%3A00.000Z",
    );
  });

  it("manages alarm rules, prefs, push and the inbox", async () => {
    request.mockResolvedValue(undefined);
    await calendarClient.addAlarm("email", 30);
    expect(request).toHaveBeenLastCalledWith("POST", "/api/calendar/alarms", { channel: "email", lead_minutes: 30 });
    await calendarClient.updateAlarm("r1", { lead_minutes: 10 });
    expect(request).toHaveBeenLastCalledWith("PATCH", "/api/calendar/alarms/r1", { lead_minutes: 10 });
    await calendarClient.removeAlarm("r1");
    expect(request).toHaveBeenLastCalledWith("DELETE", "/api/calendar/alarms/r1");
    await calendarClient.setTimezone("Europe/Madrid");
    expect(request).toHaveBeenLastCalledWith("PUT", "/api/calendar/prefs", { timezone: "Europe/Madrid" });
    await calendarClient.subscribePush({ endpoint: "https://p/1", keys: { p256dh: "k", auth: "a" } });
    expect(request).toHaveBeenLastCalledWith("POST", "/api/calendar/push/subscribe", { endpoint: "https://p/1", keys: { p256dh: "k", auth: "a" } });
    await calendarClient.unsubscribePush("https://p/1");
    expect(request).toHaveBeenLastCalledWith("POST", "/api/calendar/push/unsubscribe", { endpoint: "https://p/1" });
    await calendarClient.unseenAlerts();
    expect(request).toHaveBeenLastCalledWith("GET", "/api/calendar/alerts?unseen=1");
    await calendarClient.markSeen("a1");
    expect(request).toHaveBeenLastCalledWith("POST", "/api/calendar/alerts/a1/seen");
  });

  it("reads the admin channel switches from the settings route", async () => {
    request.mockResolvedValue({ force_tool_approval: false, calendar_inapp: true, calendar_email: false, calendar_push: true });
    expect(await calendarClient.channelSwitches()).toEqual({ inapp: true, email: false, push: true });
    expect(request).toHaveBeenLastCalledWith("GET", "/api/settings");
  });
});
```

Create `src/features/calendar/utils/eventDetails.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { findTeamsLink, isTeamsMeeting, linkify, readableUrl, splitDescription } from "./eventDetails";

describe("readableUrl", () => {
  it("accepts http(s) and unwraps Outlook safelinks", () => {
    expect(readableUrl("https://example.com/a")?.href).toBe("https://example.com/a");
    const safe = "https://eur01.safelinks.protection.outlook.com/?url=" + encodeURIComponent("https://example.com/b") + "&data=x";
    expect(readableUrl(safe)?.href).toBe("https://example.com/b");
  });
  it("refuses other schemes and junk", () => {
    expect(readableUrl("javascript:alert(1)")).toBeNull();
    expect(readableUrl("not a url")).toBeNull();
  });
});

describe("Teams links", () => {
  it("recognises meetup-join and meet links only on teams.microsoft.com", () => {
    expect(isTeamsMeeting(new URL("https://teams.microsoft.com/l/meetup-join/abc"))).toBe(true);
    expect(isTeamsMeeting(new URL("https://teams.microsoft.com/meet/123"))).toBe(true);
    expect(isTeamsMeeting(new URL("https://evil.example/teams.microsoft.com/l/meetup-join/abc"))).toBe(false);
    expect(isTeamsMeeting(null)).toBe(false);
  });
  it("finds the first meeting link across texts", () => {
    expect(findTeamsLink("see https://example.com", "join https://teams.microsoft.com/l/meetup-join/abc now")).toBe(
      "https://teams.microsoft.com/l/meetup-join/abc",
    );
    expect(findTeamsLink("nothing here")).toBeNull();
  });
});

describe("splitDescription", () => {
  it("moves the Teams footer out of the description", () => {
    const text = "Agenda\n\nMicrosoft Teams meeting\nJoin: https://teams.microsoft.com/l/meetup-join/x";
    expect(splitDescription(text)).toEqual({
      description: "Agenda",
      footer: "Microsoft Teams meeting\nJoin: https://teams.microsoft.com/l/meetup-join/x",
    });
  });
  it("keeps plain text whole", () => {
    expect(splitDescription("Just words")).toEqual({ description: "Just words", footer: "" });
  });
});

describe("linkify", () => {
  it("splits text into plain and link parts and labels Teams links", () => {
    expect(linkify("a https://teams.microsoft.com/l/meetup-join/x b")).toEqual([
      { text: "a " },
      { href: "https://teams.microsoft.com/l/meetup-join/x", label: "Join Teams meeting" },
      { text: " b" },
    ]);
  });
  it("never produces a link for a blocked scheme", () => {
    expect(linkify("go to ftp://x")).toEqual([{ text: "go to ftp://x" }]);
  });
});
```

- [ ] **Step 3: Run to verify failure**

Run: `cd apps/Ember/ember_web && npx vitest run src/features/calendar`
Expected: FAIL (modules not found).

- [ ] **Step 4: Implement**

Create `src/features/calendar/api/CalendarClient.ts`:

```ts
import { apiRequest } from "../../../api/http";

export type AlarmChannel = "inapp" | "email" | "push";

export interface CalendarFeed {
  id: string;
  name: string;
  color: string;
  enabled: boolean;
  last_fetch_at: string | null;
  last_error: string | null;
}

export interface FeedInput {
  name: string;
  url: string;
  color: string;
}

export interface EventSource {
  name: string;
  color: string;
}

export interface CalendarEvent {
  uid: string;
  title: string;
  start: string;
  end: string;
  all_day: boolean;
  location: string;
  description: string;
  sources: EventSource[];
}

export interface FeedProblem {
  feed: string;
  message: string;
}

export interface EventsReply {
  events: CalendarEvent[];
  errors: FeedProblem[];
}

export interface AlarmRule {
  id: string;
  channel: AlarmChannel;
  lead_minutes: number;
  enabled: boolean;
}

export interface CalendarAlert {
  id: string;
  title: string;
  start_utc: string;
  channel: AlarmChannel;
  created_at: string;
}

export interface Prefs {
  timezone: string;
  saved: boolean;
}

/** What the administrator has left on for everyone. */
export type ChannelSwitches = Record<AlarmChannel, boolean>;

const BASE = "/api/calendar";

export const calendarClient = {
  feeds: () => apiRequest<CalendarFeed[]>("GET", `${BASE}/feeds`),
  addFeed: (body: FeedInput) => apiRequest<CalendarFeed>("POST", `${BASE}/feeds`, body),
  updateFeed: (id: string, body: Partial<FeedInput> & { enabled?: boolean }) =>
    apiRequest<CalendarFeed>("PATCH", `${BASE}/feeds/${id}`, body),
  removeFeed: (id: string) => apiRequest<void>("DELETE", `${BASE}/feeds/${id}`),
  events: (from: Date, to: Date) =>
    apiRequest<EventsReply>(
      "GET",
      `${BASE}/events?from=${encodeURIComponent(from.toISOString())}&to=${encodeURIComponent(to.toISOString())}`,
    ),
  alarms: () => apiRequest<AlarmRule[]>("GET", `${BASE}/alarms`),
  addAlarm: (channel: AlarmChannel, lead_minutes: number) =>
    apiRequest<AlarmRule>("POST", `${BASE}/alarms`, { channel, lead_minutes }),
  updateAlarm: (id: string, body: Partial<Pick<AlarmRule, "channel" | "lead_minutes" | "enabled">>) =>
    apiRequest<AlarmRule>("PATCH", `${BASE}/alarms/${id}`, body),
  removeAlarm: (id: string) => apiRequest<void>("DELETE", `${BASE}/alarms/${id}`),
  prefs: () => apiRequest<Prefs>("GET", `${BASE}/prefs`),
  setTimezone: (timezone: string) => apiRequest<Prefs>("PUT", `${BASE}/prefs`, { timezone }),
  pushKey: async (): Promise<string> => (await apiRequest<{ key: string }>("GET", `${BASE}/push/key`)).key,
  subscribePush: (body: { endpoint: string; keys: { p256dh: string; auth: string } }) =>
    apiRequest<void>("POST", `${BASE}/push/subscribe`, body),
  unsubscribePush: (endpoint: string) => apiRequest<void>("POST", `${BASE}/push/unsubscribe`, { endpoint }),
  unseenAlerts: () => apiRequest<CalendarAlert[]>("GET", `${BASE}/alerts?unseen=1`),
  markSeen: (id: string) => apiRequest<void>("POST", `${BASE}/alerts/${id}/seen`),
  channelSwitches: async (): Promise<ChannelSwitches> => {
    const settings = await apiRequest<Record<string, boolean>>("GET", "/api/settings");
    return {
      inapp: settings.calendar_inapp !== false,
      email: settings.calendar_email !== false,
      push: settings.calendar_push !== false,
    };
  },
};
```

Create `src/features/calendar/utils/eventDetails.ts`:

```ts
/** Reading an event's free text safely: links, the Teams join link, and the boilerplate footer Outlook adds. */

export type TextPart = { text: string } | { href: string; label: string };

const WEB = ["https:", "http:"];
const URL_PATTERN = /https?:\/\/[^\s<>"']+/gi;
const FOOTER = /^\s*(?:Microsoft Teams(?: meeting)?\s*$|Join (?:the )?meeting(?: now)?\s*$|_{5,}|-{10,})/im;

/** An http(s) URL; an Outlook safelink is replaced by the address it protects. */
export function readableUrl(raw: string): URL | null {
  try {
    const url = new URL(raw);
    if (!WEB.includes(url.protocol)) return null;
    if (url.hostname.endsWith(".safelinks.protection.outlook.com")) {
      const target = url.searchParams.get("url");
      if (target) {
        const inner = new URL(target);
        if (WEB.includes(inner.protocol)) return inner;
      }
    }
    return url;
  } catch {
    return null;
  }
}

export function isTeamsMeeting(url: URL | null): boolean {
  return url !== null && url.hostname === "teams.microsoft.com" && /^\/(?:l\/meetup-join\/|meet\/)/i.test(url.pathname);
}

export function findTeamsLink(...texts: string[]): string | null {
  for (const match of texts.filter(Boolean).join(" ").matchAll(URL_PATTERN)) {
    const url = readableUrl(match[0]);
    if (isTeamsMeeting(url)) return url!.href;
  }
  return null;
}

export function splitDescription(text: string): { description: string; footer: string } {
  const value = (text || "").replace(/\r\n/g, "\n");
  const footer = FOOTER.exec(value);
  if (!footer) return { description: value.trim(), footer: "" };
  return {
    description: value.slice(0, footer.index).trim(),
    footer: value.slice(footer.index).replace(/^\s*[_-]{5,}\s*/g, "").trim(),
  };
}

/** Text as parts a template can render without v-html: plain text, or a safe link. */
export function linkify(text: string): TextPart[] {
  const value = text || "";
  const parts: TextPart[] = [];
  let offset = 0;
  for (const match of value.matchAll(URL_PATTERN)) {
    const url = readableUrl(match[0]);
    if (!url) continue;
    if (match.index! > offset) parts.push({ text: value.slice(offset, match.index) });
    parts.push({ href: url.href, label: isTeamsMeeting(url) ? "Join Teams meeting" : "Open link" });
    offset = match.index! + match[0].length;
  }
  if (offset < value.length) parts.push({ text: value.slice(offset) });
  return parts;
}
```

Create `src/features/calendar/utils/palette.ts`:

```ts
/** Default colors offered to a new calendar (user data, so literal values are fine here). */
export const FEED_COLORS: readonly string[] = ["#2563eb", "#dc2626", "#d97706", "#7c3aed", "#0891b2", "#db2777"];

export function nextFeedColor(used: readonly string[]): string {
  return FEED_COLORS.find((color) => !used.includes(color)) ?? FEED_COLORS[used.length % FEED_COLORS.length]!;
}
```

- [ ] **Step 5: Run to verify pass**

Run: `cd apps/Ember/ember_web && npx vitest run src/features/calendar && npx vue-tsc -b`
Expected: PASS; no type errors.

- [ ] **Step 6: Commit**

```bash
git add apps/Ember/ember_web/package.json apps/Ember/ember_web/package-lock.json apps/Ember/ember_web/src/features/calendar
git commit -m "feat(calendar): web client, event text utilities and FullCalendar dependencies"
```

---

### Task 11: Calendar store, page and panels

**Files:**
- Create: `apps/Ember/ember_web/src/features/calendar/stores/calendar.ts`
- Create: `apps/Ember/ember_web/src/features/calendar/stores/calendar.test.ts`
- Create: `apps/Ember/ember_web/src/features/calendar/CalendarView.vue`
- Create: `apps/Ember/ember_web/src/features/calendar/components/FeedsPanel.vue`
- Create: `apps/Ember/ember_web/src/features/calendar/components/AlertRulesPanel.vue`
- Create: `apps/Ember/ember_web/src/features/calendar/components/EventDialog.vue`
- Create: `apps/Ember/ember_web/src/features/calendar/composables/usePushSubscription.ts` (+ `.test.ts`)

**Interfaces:**
- Consumes: Task 10 exports; `useAuthStore` (`stores/auth`, has `account`); `errorMessage` from `utils/errors`; `PageLayout`, `ConfirmModal`, `BaseModal`, `ToggleSwitch`.
- Produces: `useCalendarStore()` with refs `feeds`, `rules`, `switches`, `problems`, `error`, `ready` and actions `loadSetup()`, `loadEvents(from, to): Promise<CalendarEvent[]>`, `addFeed(input)`, `updateFeed(id, patch)`, `removeFeed(id)`, `addRule(channel, lead)`, `updateRule(id, patch)`, `removeRule(id)`; push helpers `urlBase64ToUint8Array(base64: string): Uint8Array`, `pushSupported(): boolean`, `enablePush(): Promise<string>` (error message or `""`), `disablePush(): Promise<void>`, `currentPushEndpoint(): Promise<string | null>`.

- [ ] **Step 1: Write the failing store and push-helper tests**

Create `src/features/calendar/stores/calendar.test.ts`:

```ts
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { calendarClient } from "../api/CalendarClient";
import { useAuthStore } from "../../../stores/auth";
import { useCalendarStore } from "./calendar";

vi.mock("../api/CalendarClient", () => ({
  calendarClient: {
    feeds: vi.fn(), alarms: vi.fn(), prefs: vi.fn(), channelSwitches: vi.fn(), setTimezone: vi.fn(),
    events: vi.fn(), addFeed: vi.fn(), updateFeed: vi.fn(), removeFeed: vi.fn(),
    addAlarm: vi.fn(), updateAlarm: vi.fn(), removeAlarm: vi.fn(),
  },
}));
const client = vi.mocked(calendarClient);

const FEED = { id: "f1", name: "Work", color: "#2563eb", enabled: true, last_fetch_at: null, last_error: null };
const RULE = { id: "r1", channel: "inapp" as const, lead_minutes: 15, enabled: true };

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  useAuthStore().account = { id: 1 } as never;
  client.feeds.mockResolvedValue([FEED]);
  client.alarms.mockResolvedValue([RULE]);
  client.prefs.mockResolvedValue({ timezone: "UTC", saved: true });
  client.channelSwitches.mockResolvedValue({ inapp: true, email: true, push: false });
});

describe("calendar store", () => {
  it("loads feeds, rules and the admin switches together", async () => {
    const store = useCalendarStore();
    await store.loadSetup();
    expect(store.feeds).toEqual([FEED]);
    expect(store.rules).toEqual([RULE]);
    expect(store.switches.push).toBe(false);
    expect(store.ready).toBe(true);
  });

  it("saves the browser time zone on the first visit only", async () => {
    client.prefs.mockResolvedValue({ timezone: "UTC", saved: false });
    client.setTimezone.mockResolvedValue({ timezone: "Europe/Madrid", saved: true });
    vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({ timeZone: "Europe/Madrid" } as never);
    await useCalendarStore().loadSetup();
    expect(client.setTimezone).toHaveBeenCalledWith("Europe/Madrid");
  });

  it("keeps the problems the server reports with the events", async () => {
    client.events.mockResolvedValue({ events: [], errors: [{ feed: "Work", message: "HTTP 500" }] });
    const store = useCalendarStore();
    await store.loadEvents(new Date(0), new Date(1000));
    expect(store.problems).toEqual([{ feed: "Work", message: "HTTP 500" }]);
  });

  it("adds, updates and removes a feed in place", async () => {
    const store = useCalendarStore();
    await store.loadSetup();
    client.addFeed.mockResolvedValue({ ...FEED, id: "f2", name: "Team" });
    await store.addFeed({ name: "Team", url: "https://x/a.ics", color: "#dc2626" });
    expect(store.feeds.map((f) => f.id)).toEqual(["f1", "f2"]);
    client.updateFeed.mockResolvedValue({ ...FEED, enabled: false });
    await store.updateFeed("f1", { enabled: false });
    expect(store.feeds[0]!.enabled).toBe(false);
    client.removeFeed.mockResolvedValue(undefined);
    await store.removeFeed("f2");
    expect(store.feeds.map((f) => f.id)).toEqual(["f1"]);
  });

  it("ignores answers that arrive after the account changed", async () => {
    let resolve!: (value: never) => void;
    client.events.mockReturnValue(new Promise((r) => { resolve = r as never; }));
    const store = useCalendarStore();
    const pending = store.loadEvents(new Date(0), new Date(1000));
    useAuthStore().account = { id: 2 } as never;
    await Promise.resolve();
    resolve({ events: [{ uid: "x" }], errors: [{ feed: "old", message: "x" }] } as never);
    expect(await pending).toEqual([]);
    expect(store.problems).toEqual([]);
  });
});
```

Create `src/features/calendar/composables/usePushSubscription.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { urlBase64ToUint8Array } from "./usePushSubscription";

describe("urlBase64ToUint8Array", () => {
  it("decodes url-safe base64 without padding", () => {
    expect(Array.from(urlBase64ToUint8Array("AQID"))).toEqual([1, 2, 3]);
    expect(Array.from(urlBase64ToUint8Array("-_8"))).toEqual([251, 255]);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/Ember/ember_web && npx vitest run src/features/calendar`
Expected: FAIL (store and composable modules not found).

- [ ] **Step 3: Implement the store**

Create `src/features/calendar/stores/calendar.ts`:

```ts
import { defineStore } from "pinia";
import { ref, watch } from "vue";
import {
  calendarClient,
  type AlarmChannel,
  type AlarmRule,
  type CalendarEvent,
  type CalendarFeed,
  type ChannelSwitches,
  type FeedInput,
  type FeedProblem,
} from "../api/CalendarClient";
import { useAuthStore } from "../../../stores/auth";
import { errorMessage } from "../../../utils/errors";

/** The signed-in account's calendar: its feeds, alert rules and the admin's channel switches.
 * Answers that arrive after the account changed are dropped. */
export const useCalendarStore = defineStore("calendar", () => {
  const auth = useAuthStore();

  const feeds = ref<CalendarFeed[]>([]);
  const rules = ref<AlarmRule[]>([]);
  const switches = ref<ChannelSwitches>({ inapp: true, email: true, push: true });
  const problems = ref<FeedProblem[]>([]);
  const error = ref("");
  const ready = ref(false);
  let generation = 0;

  watch(
    () => auth.account?.id ?? null,
    () => {
      generation += 1;
      feeds.value = [];
      rules.value = [];
      problems.value = [];
      error.value = "";
      ready.value = false;
    },
    { immediate: true },
  );

  async function loadSetup(): Promise<void> {
    const started = generation;
    try {
      const [loadedFeeds, loadedRules, prefs, loadedSwitches] = await Promise.all([
        calendarClient.feeds(), calendarClient.alarms(), calendarClient.prefs(), calendarClient.channelSwitches(),
      ]);
      if (started !== generation) return;
      feeds.value = loadedFeeds;
      rules.value = loadedRules;
      switches.value = loadedSwitches;
      const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (!prefs.saved && zone) await calendarClient.setTimezone(zone).catch(() => undefined);
    } catch (err) {
      if (started === generation) error.value = errorMessage(err);
    } finally {
      if (started === generation) ready.value = true;
    }
  }

  async function loadEvents(from: Date, to: Date): Promise<CalendarEvent[]> {
    const started = generation;
    const reply = await calendarClient.events(from, to);
    if (started !== generation) return [];
    problems.value = reply.errors;
    return reply.events;
  }

  async function addFeed(input: FeedInput): Promise<void> {
    feeds.value = [...feeds.value, await calendarClient.addFeed(input)];
  }

  async function updateFeed(id: string, patch: Partial<FeedInput> & { enabled?: boolean }): Promise<void> {
    const updated = await calendarClient.updateFeed(id, patch);
    feeds.value = feeds.value.map((f) => (f.id === id ? updated : f));
  }

  async function removeFeed(id: string): Promise<void> {
    await calendarClient.removeFeed(id);
    feeds.value = feeds.value.filter((f) => f.id !== id);
  }

  async function addRule(channel: AlarmChannel, lead: number): Promise<void> {
    rules.value = [...rules.value, await calendarClient.addAlarm(channel, lead)].sort((a, b) => a.lead_minutes - b.lead_minutes);
  }

  async function updateRule(id: string, patch: Partial<Pick<AlarmRule, "channel" | "lead_minutes" | "enabled">>): Promise<void> {
    const updated = await calendarClient.updateAlarm(id, patch);
    rules.value = rules.value.map((r) => (r.id === id ? updated : r));
  }

  async function removeRule(id: string): Promise<void> {
    await calendarClient.removeAlarm(id);
    rules.value = rules.value.filter((r) => r.id !== id);
  }

  return { feeds, rules, switches, problems, error, ready, loadSetup, loadEvents, addFeed, updateFeed, removeFeed, addRule, updateRule, removeRule };
});

export type { CalendarEvent } from "../api/CalendarClient";
```

- [ ] **Step 4: Implement the push helper**

Create `src/features/calendar/composables/usePushSubscription.ts`:

```ts
import { calendarClient } from "../api/CalendarClient";

/** Web push for this browser. It needs the built app: the dev server registers no service worker. */

export function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padded = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(padded);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export function pushSupported(): boolean {
  return typeof navigator !== "undefined" && "serviceWorker" in navigator && typeof PushManager !== "undefined" && typeof Notification !== "undefined";
}

async function registration(): Promise<ServiceWorkerRegistration | null> {
  const timeout = new Promise<null>((resolve) => setTimeout(() => resolve(null), 4000));
  return Promise.race([navigator.serviceWorker.ready, timeout]);
}

export async function currentPushEndpoint(): Promise<string | null> {
  if (!pushSupported()) return null;
  const reg = await registration();
  return (await reg?.pushManager.getSubscription())?.endpoint ?? null;
}

/** Call from a click. Returns a message to show, or "" when this browser is now subscribed. */
export async function enablePush(): Promise<string> {
  if (!pushSupported()) return "This browser does not support push alerts.";
  try {
    const permission = Notification.permission === "default" ? await Notification.requestPermission() : Notification.permission;
    if (permission !== "granted") return "Notifications are blocked. Allow them in your browser's site settings, then try again.";
    const reg = await registration();
    if (!reg) return "Push alerts need the installed or built Ember app (not the dev server) over HTTPS.";
    const key = await calendarClient.pushKey();
    const subscription =
      (await reg.pushManager.getSubscription()) ??
      (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(key) as BufferSource }));
    const json = subscription.toJSON();
    if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth) return "The browser gave an incomplete push subscription.";
    await calendarClient.subscribePush({ endpoint: json.endpoint, keys: { p256dh: json.keys.p256dh, auth: json.keys.auth } });
    return "";
  } catch {
    return "Push alerts could not be turned on in this browser.";
  }
}

export async function disablePush(): Promise<void> {
  const reg = pushSupported() ? await registration() : null;
  const subscription = await reg?.pushManager.getSubscription();
  if (!subscription) return;
  await calendarClient.unsubscribePush(subscription.endpoint).catch(() => undefined);
  await subscription.unsubscribe();
}
```

- [ ] **Step 5: Implement the components**

Create `src/features/calendar/components/FeedsPanel.vue`:

```vue
<script setup lang="ts">
import { computed, ref } from "vue";
import ConfirmModal from "../../../components/ui/dialogs/ConfirmModal.vue";
import ToggleSwitch from "../../../components/ui/forms/ToggleSwitch.vue";
import { errorMessage } from "../../../utils/errors";
import type { CalendarFeed } from "../api/CalendarClient";
import { nextFeedColor } from "../utils/palette";
import { useCalendarStore } from "../stores/calendar";

/** Calendar links: add, show/hide, recolor, rename and remove. The link itself is never shown again after saving. */
const emit = defineEmits<{ changed: [] }>();
const calendar = useCalendarStore();

const name = ref("");
const url = ref("");
const formError = ref("");
const busy = ref(false);
const removing = ref<CalendarFeed | null>(null);
const rowError = ref("");

const color = computed(() => nextFeedColor(calendar.feeds.map((f) => f.color)));

async function add(): Promise<void> {
  formError.value = "";
  busy.value = true;
  try {
    await calendar.addFeed({ name: name.value.trim() || "Calendar", url: url.value, color: color.value });
    name.value = "";
    url.value = "";
    emit("changed");
  } catch (err) {
    formError.value = errorMessage(err);
  } finally {
    busy.value = false;
  }
}

async function change(feed: CalendarFeed, patch: { name?: string; color?: string; enabled?: boolean }): Promise<void> {
  rowError.value = "";
  try {
    await calendar.updateFeed(feed.id, patch);
    emit("changed");
  } catch (err) {
    rowError.value = errorMessage(err);
  }
}

async function remove(): Promise<void> {
  const feed = removing.value;
  if (!feed) return;
  busy.value = true;
  try {
    await calendar.removeFeed(feed.id);
    removing.value = null;
    emit("changed");
  } catch (err) {
    rowError.value = errorMessage(err);
    removing.value = null;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="panel" aria-labelledby="feeds-title">
    <h3 id="feeds-title">My calendars</h3>
    <ul v-if="calendar.feeds.length" class="feeds" aria-label="Calendars">
      <li v-for="feed in calendar.feeds" :key="feed.id" class="feed">
        <ToggleSwitch small :checked="feed.enabled" :aria-label="`Show ${feed.name}`" @change="change(feed, { enabled: !feed.enabled })" />
        <input class="swatch" type="color" :value="feed.color" :aria-label="`Color of ${feed.name}`" @change="change(feed, { color: ($event.target as HTMLInputElement).value })" />
        <input class="name" type="text" :value="feed.name" maxlength="60" :aria-label="`Name of calendar ${feed.name}`" @change="change(feed, { name: ($event.target as HTMLInputElement).value })" />
        <button type="button" class="chip" :aria-label="`Remove ${feed.name}`" @click="removing = feed">Remove</button>
        <p v-if="feed.last_error" class="problem" role="status">Could not refresh: {{ feed.last_error }}</p>
      </li>
    </ul>
    <p v-else class="muted">No calendars yet. Paste a published ICS link below.</p>
    <p v-if="rowError" class="problem" role="alert">{{ rowError }}</p>

    <form class="add" @submit.prevent="add">
      <label>Label<input v-model="name" type="text" maxlength="60" autocomplete="off" placeholder="Work" /></label>
      <label>
        ICS link
        <input v-model="url" type="url" required autocomplete="off" inputmode="url" placeholder="https://… or webcal://…" :aria-invalid="formError ? 'true' : undefined" aria-describedby="feed-error" />
      </label>
      <p id="feed-error" class="problem" role="alert">{{ formError }}</p>
      <button type="submit" class="primary" :disabled="busy" :aria-busy="busy">Add calendar</button>
    </form>

    <ConfirmModal
      :open="removing !== null"
      title="Remove calendar"
      :message="`Remove ${removing?.name ?? ''}? Its events disappear from your schedule. The calendar itself is not touched.`"
      confirm-label="Remove"
      danger
      :busy="busy"
      @confirm="remove"
      @close="removing = null"
    />
  </section>
</template>

<style scoped>
.panel { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
h3 { margin: 0; font-size: 1rem; }
.feeds { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.feed { display: grid; grid-template-columns: auto auto minmax(0, 1fr) auto; align-items: center; gap: 8px; }
.feed .problem { grid-column: 1 / -1; }
.swatch { width: 28px; height: 28px; padding: 0; border: 1px solid var(--border); border-radius: var(--radius-full); background: none; }
.name, .add input { min-width: 0; min-height: 36px; padding: 4px 8px; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-md); font: inherit; }
.add { display: grid; gap: 8px; }
.add label { display: grid; gap: 4px; font-size: 0.85rem; color: var(--muted); }
.problem { margin: 0; min-height: 1em; font-size: 0.85rem; color: var(--danger); }
.muted { margin: 0; color: var(--muted); font-size: 0.9rem; }
.primary { min-height: 40px; color: var(--accent-contrast); background: var(--accent); border: 0; border-radius: var(--radius-md); font: inherit; font-weight: 600; cursor: pointer; }
.chip { min-height: 32px; padding: 0 10px; color: var(--text); background: transparent; border: 1px solid var(--border); border-radius: var(--radius-md); font: inherit; cursor: pointer; }
</style>
```

Create `src/features/calendar/components/AlertRulesPanel.vue`:

```vue
<script setup lang="ts">
import { onMounted, ref } from "vue";
import ToggleSwitch from "../../../components/ui/forms/ToggleSwitch.vue";
import { errorMessage } from "../../../utils/errors";
import type { AlarmChannel, AlarmRule } from "../api/CalendarClient";
import { currentPushEndpoint, disablePush, enablePush, pushSupported } from "../composables/usePushSubscription";
import { useCalendarStore } from "../stores/calendar";

/** Alert rules: which way (in-app, email, push) and how long before. Each rule fires once per event. */
const calendar = useCalendarStore();

const CHANNELS: { id: AlarmChannel; label: string }[] = [
  { id: "inapp", label: "In Ember" },
  { id: "email", label: "Email" },
  { id: "push", label: "Push notification" },
];
const LEADS = [5, 10, 15, 30, 60, 120, 1440];

const channel = ref<AlarmChannel>("inapp");
const lead = ref(15);
const error = ref("");
const pushMessage = ref("");
const pushOn = ref(false);

onMounted(async () => {
  pushOn.value = (await currentPushEndpoint()) !== null;
});

function label(id: AlarmChannel): string {
  return CHANNELS.find((c) => c.id === id)?.label ?? id;
}

function leadText(minutes: number): string {
  if (minutes % 1440 === 0) return minutes === 1440 ? "1 day before" : `${minutes / 1440} days before`;
  if (minutes % 60 === 0) return minutes === 60 ? "1 hour before" : `${minutes / 60} hours before`;
  return `${minutes} minutes before`;
}

function available(id: AlarmChannel): boolean {
  return calendar.switches[id];
}

async function run(action: () => Promise<void>): Promise<void> {
  error.value = "";
  try {
    await action();
  } catch (err) {
    error.value = errorMessage(err);
  }
}

const add = () => run(() => calendar.addRule(channel.value, lead.value));
const toggle = (rule: AlarmRule) => run(() => calendar.updateRule(rule.id, { enabled: !rule.enabled }));
const retime = (rule: AlarmRule, minutes: number) => run(() => calendar.updateRule(rule.id, { lead_minutes: minutes }));
const remove = (rule: AlarmRule) => run(() => calendar.removeRule(rule.id));

async function turnPushOn(): Promise<void> {
  pushMessage.value = await enablePush();
  pushOn.value = pushMessage.value === "";
}

async function turnPushOff(): Promise<void> {
  await disablePush();
  pushOn.value = false;
}
</script>

<template>
  <section class="panel" aria-labelledby="alerts-title">
    <h3 id="alerts-title">Alerts</h3>
    <ul v-if="calendar.rules.length" class="rules" aria-label="Alert rules">
      <li v-for="rule in calendar.rules" :key="rule.id" class="rule">
        <ToggleSwitch small :checked="rule.enabled && available(rule.channel)" :disabled="!available(rule.channel)" :aria-label="`${label(rule.channel)}, ${leadText(rule.lead_minutes)}`" @change="toggle(rule)" />
        <span class="what">
          {{ label(rule.channel) }}
          <select :value="rule.lead_minutes" :aria-label="`Lead time for ${label(rule.channel)}`" @change="retime(rule, Number(($event.target as HTMLSelectElement).value))">
            <option v-for="m in LEADS" :key="m" :value="m">{{ leadText(m) }}</option>
            <option v-if="!LEADS.includes(rule.lead_minutes)" :value="rule.lead_minutes">{{ leadText(rule.lead_minutes) }}</option>
          </select>
        </span>
        <button type="button" class="chip" :aria-label="`Remove ${label(rule.channel)} alert ${leadText(rule.lead_minutes)}`" @click="remove(rule)">Remove</button>
        <p v-if="!available(rule.channel)" class="muted">Switched off by an administrator.</p>
      </li>
    </ul>
    <p v-else class="muted">No alerts. Add one below.</p>

    <form class="add" @submit.prevent="add">
      <label>Type
        <select v-model="channel">
          <option v-for="c in CHANNELS" :key="c.id" :value="c.id" :disabled="!available(c.id)">{{ c.label }}{{ available(c.id) ? "" : " (off)" }}</option>
        </select>
      </label>
      <label>When
        <select v-model.number="lead"><option v-for="m in LEADS" :key="m" :value="m">{{ leadText(m) }}</option></select>
      </label>
      <button type="submit" class="primary">Add alert</button>
    </form>
    <p v-if="error" class="problem" role="alert">{{ error }}</p>

    <div v-if="calendar.switches.push && pushSupported()" class="push">
      <span>Push on this device: <strong>{{ pushOn ? "on" : "off" }}</strong></span>
      <button v-if="!pushOn" type="button" class="chip" @click="turnPushOn">Turn on</button>
      <button v-else type="button" class="chip" @click="turnPushOff">Turn off</button>
      <p v-if="pushMessage" class="problem" role="status">{{ pushMessage }}</p>
    </div>
  </section>
</template>

<style scoped>
.panel { display: grid; gap: 10px; padding: 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); }
h3 { margin: 0; font-size: 1rem; }
.rules { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.rule { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 8px; }
.rule .muted { grid-column: 1 / -1; }
.what { display: grid; gap: 4px; min-width: 0; }
select { min-height: 36px; padding: 4px 8px; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-md); font: inherit; }
.add { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; align-items: end; }
.add label { display: grid; gap: 4px; font-size: 0.85rem; color: var(--muted); }
.add .primary { grid-column: 1 / -1; }
.push { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 0.9rem; }
.problem { margin: 0; font-size: 0.85rem; color: var(--danger); }
.muted { margin: 0; color: var(--muted); font-size: 0.85rem; }
.primary { min-height: 40px; color: var(--accent-contrast); background: var(--accent); border: 0; border-radius: var(--radius-md); font: inherit; font-weight: 600; cursor: pointer; }
.chip { min-height: 32px; padding: 0 10px; color: var(--text); background: transparent; border: 1px solid var(--border); border-radius: var(--radius-md); font: inherit; cursor: pointer; }
</style>
```

Create `src/features/calendar/components/EventDialog.vue`:

```vue
<script setup lang="ts">
import { computed } from "vue";
import BaseModal from "../../../components/ui/dialogs/BaseModal.vue";
import type { CalendarEvent } from "../api/CalendarClient";
import { findTeamsLink, linkify, splitDescription } from "../utils/eventDetails";

const props = defineProps<{ event: CalendarEvent | null }>();
const emit = defineEmits<{ close: [] }>();

const when = computed(() => {
  const e = props.event;
  if (!e) return "";
  const start = new Date(e.start);
  if (e.all_day) return start.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" }) + " · All day";
  const end = new Date(e.end);
  const day = start.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" });
  const time = { hour: "numeric", minute: "2-digit" } as const;
  return `${day} · ${start.toLocaleTimeString(undefined, time)} – ${end.toLocaleTimeString(undefined, time)}`;
});
const parts = computed(() => splitDescription(props.event?.description ?? ""));
const join = computed(() => (props.event ? findTeamsLink(props.event.description, props.event.location) : null));
</script>

<template>
  <BaseModal :open="event !== null" :title="event?.title ?? ''" @close="emit('close')">
    <div v-if="event" class="details">
      <p class="sources">
        <span v-for="s in event.sources" :key="s.name" class="badge"><i class="dot" :style="{ background: s.color }" />{{ s.name }}</span>
      </p>
      <p class="when">{{ when }}</p>
      <p v-if="event.location" class="where">
        <template v-for="(part, i) in linkify(event.location)" :key="i">
          <a v-if="'href' in part" :href="part.href" target="_blank" rel="noopener noreferrer">{{ part.label }}</a>
          <template v-else>{{ part.text }}</template>
        </template>
      </p>
      <a v-if="join" class="join" :href="join" target="_blank" rel="noopener noreferrer">Join Teams meeting</a>
      <pre class="description"><template v-for="(part, i) in linkify(parts.description || 'No additional description.')" :key="i"><a v-if="'href' in part" :href="part.href" target="_blank" rel="noopener noreferrer">{{ part.label }}</a><template v-else>{{ part.text }}</template></template></pre>
      <details v-if="parts.footer" class="footer">
        <summary>Meeting information &amp; original details</summary>
        <pre><template v-for="(part, i) in linkify(parts.footer)" :key="i"><a v-if="'href' in part" :href="part.href" target="_blank" rel="noopener noreferrer">{{ part.label }}</a><template v-else>{{ part.text }}</template></template></pre>
      </details>
    </div>
  </BaseModal>
</template>

<style scoped>
.details { display: grid; gap: 12px; min-width: 0; }
.sources { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 0.8rem; }
.dot { width: 10px; height: 10px; border-radius: var(--radius-full); }
.when, .where { margin: 0; overflow-wrap: anywhere; }
.when { font-weight: 600; }
.join { justify-self: start; padding: 10px 18px; color: var(--accent-contrast); background: var(--accent); border-radius: var(--radius-md); font-weight: 600; text-decoration: none; }
pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; color: var(--muted); max-height: 40vh; overflow: auto; }
a { color: var(--accent); }
.footer summary { cursor: pointer; font-weight: 600; }
</style>
```

Create `src/features/calendar/CalendarView.vue`:

```vue
<script setup lang="ts">
import type { CalendarOptions, EventClickArg, EventInput } from "@fullcalendar/core";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import FullCalendar from "@fullcalendar/vue3";
import { onBeforeUnmount, onMounted, ref } from "vue";
import PageLayout from "../../components/layout/PageLayout.vue";
import "../../components/layout/infoPage.css";
import AlertRulesPanel from "./components/AlertRulesPanel.vue";
import EventDialog from "./components/EventDialog.vue";
import FeedsPanel from "./components/FeedsPanel.vue";
import { useCalendarStore, type CalendarEvent } from "./stores/calendar";

/** The account's read-only schedule from its ICS links, with the alert rules beside it. */
const calendar = useCalendarStore();
const grid = ref<InstanceType<typeof FullCalendar> | null>(null);
const selected = ref<CalendarEvent | null>(null);

function toInput(e: CalendarEvent): EventInput {
  const color = e.sources[0]?.color;
  return { id: `${e.uid}|${e.start}`, title: e.title, start: e.start, end: e.end, allDay: e.all_day, backgroundColor: color, borderColor: color, extendedProps: { source: e } };
}

const options: CalendarOptions = {
  plugins: [dayGridPlugin, timeGridPlugin],
  initialView: "workWeek",
  views: { workWeek: { type: "timeGridWeek", weekends: false } },
  headerToolbar: { left: "today prev,next", center: "title", right: "timeGridDay,workWeek,timeGridWeek,dayGridMonth" },
  buttonText: { today: "Today", timeGridDay: "Day", workWeek: "Work week", timeGridWeek: "Week", dayGridMonth: "Month" },
  firstDay: 1,
  height: "100%",
  nowIndicator: true,
  slotDuration: "00:30:00",
  allDaySlot: true,
  eventDidMount: (info) => info.el.style.setProperty("--event-color", info.event.backgroundColor || "var(--accent)"),
  events: (info, success, failure) => {
    calendar.loadEvents(info.start, info.end).then((list) => success(list.map(toInput)), failure);
  },
  eventClick: (arg: EventClickArg) => {
    selected.value = arg.event.extendedProps.source as CalendarEvent;
  },
};

const refetch = () => grid.value?.getApi().refetchEvents();
let timer: ReturnType<typeof setInterval> | undefined;
const onVisible = () => { if (!document.hidden) refetch(); };

onMounted(() => {
  void calendar.loadSetup();
  timer = setInterval(refetch, 5 * 60_000);
  document.addEventListener("visibilitychange", onVisible);
});
onBeforeUnmount(() => {
  clearInterval(timer);
  document.removeEventListener("visibilitychange", onVisible);
});
</script>

<template>
  <PageLayout title="Calendar" description="Your read-only schedule from ICS links, with alerts before events." class="calendar info-content" wide fill>
    <p v-if="calendar.error" class="problem" role="alert">{{ calendar.error }}</p>
    <div class="workspace">
      <aside class="side" aria-label="Calendar settings">
        <FeedsPanel @changed="refetch" />
        <AlertRulesPanel />
      </aside>
      <section class="grid" aria-label="Schedule">
        <ul v-if="calendar.problems.length" class="issues" role="status">
          <li v-for="p in calendar.problems" :key="p.feed">⚠ {{ p.feed }}: {{ p.message }}</li>
        </ul>
        <FullCalendar ref="grid" :options="options" class="fc-host" />
      </section>
    </div>
    <EventDialog :event="selected" @close="selected = null" />
  </PageLayout>
</template>

<style scoped>
.workspace { display: grid; grid-template-columns: minmax(260px, 320px) minmax(0, 1fr); gap: 16px; min-height: 0; flex: 1; }
.side { display: grid; align-content: start; gap: 12px; min-height: 0; overflow: auto; }
.grid { display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.fc-host { flex: 1; min-height: 520px; }
.issues { margin: 0 0 8px; padding: 8px 12px; list-style: none; color: var(--warning); border: 1px solid var(--border); border-radius: var(--radius-md); font-size: 0.85rem; }
.problem { color: var(--danger); }
@media (max-width: 767px) {
  .workspace { grid-template-columns: minmax(0, 1fr); }
  .side { overflow: visible; }
}
.calendar :deep(.fc) {
  --fc-border-color: var(--border);
  --fc-page-bg-color: var(--bg);
  --fc-neutral-bg-color: var(--surface);
  --fc-today-bg-color: color-mix(in srgb, var(--accent) 8%, transparent);
  --fc-now-indicator-color: var(--accent);
  --fc-event-border-color: transparent;
  color: var(--text);
}
.calendar :deep(.fc .fc-button) { color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-md); box-shadow: none; text-transform: none; }
.calendar :deep(.fc .fc-button-active), .calendar :deep(.fc .fc-button:hover) { color: var(--accent-contrast); background: var(--accent); border-color: var(--accent); }
.calendar :deep(.fc .fc-event) {
  color: var(--text);
  background: color-mix(in srgb, var(--event-color, var(--accent)) 18%, var(--bg));
  border: 0;
  border-left: 4px solid var(--event-color, var(--accent));
  border-radius: var(--radius-sm);
}
.calendar :deep(.fc .fc-col-header-cell-cushion), .calendar :deep(.fc .fc-daygrid-day-number), .calendar :deep(.fc .fc-timegrid-slot-label-cushion) { color: var(--muted); text-decoration: none; }
</style>
```

- [ ] **Step 6: Run checks**

Run: `cd apps/Ember/ember_web && npx vitest run src/features/calendar && npx vue-tsc -b`
Expected: store and push-helper tests PASS; `vue-tsc` clean. Fix any prop-type mismatch with `BaseModal` (its props are `open` and `title`, default slot for the body) or `ToggleSwitch` (it forwards `checked`, `disabled`, `aria-label` and `change` to the inner checkbox via `$attrs`).

- [ ] **Step 7: Commit**

```bash
git add apps/Ember/ember_web/src/features/calendar
git commit -m "feat(calendar): calendar page, feed and alert panels, event dialog and store"
```

---

### Task 12: Route, nav entry, in-app alerts and push worker

**Files:**
- Modify: `apps/Ember/ember_web/src/router/index.ts`
- Modify: `apps/Ember/ember_web/src/router/pages.ts`
- Modify: `apps/Ember/ember_web/src/App.vue`
- Modify: `apps/Ember/ember_web/vite.config.ts`
- Create: `apps/Ember/ember_web/public/push-sw.js`
- Create: `apps/Ember/ember_web/src/features/calendar/composables/useAlertPoller.ts` (+ `.test.ts`)
- Create: `apps/Ember/ember_web/src/features/calendar/components/AlertToasts.vue`

**Interfaces:**
- Consumes: `calendarClient.unseenAlerts`, `calendarClient.markSeen`, `CalendarAlert` (Task 10); `useAuthStore` (`account`, `needsVerification`, `hasPermission`).
- Produces: `useAlertPoller()` returning `{ alerts: Ref<CalendarAlert[]>, dismiss(id: string): Promise<void>, poll(): Promise<void> }` and starting a 30 s poll while a calendar-permitted account is logged in; `AlertToasts.vue` (no props) mounted once in `App.vue`.

- [ ] **Step 1: Write the failing poller test**

Create `src/features/calendar/composables/useAlertPoller.test.ts`:

```ts
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, nextTick } from "vue";
import { calendarClient } from "../api/CalendarClient";
import { useAuthStore } from "../../../stores/auth";
import { useAlertPoller } from "./useAlertPoller";

vi.mock("../api/CalendarClient", () => ({ calendarClient: { unseenAlerts: vi.fn(), markSeen: vi.fn() } }));
const client = vi.mocked(calendarClient);

const soon = () => new Date(Date.now() + 10 * 60_000).toISOString();
const ALERT = { id: "a1", title: "Standup", start_utc: soon(), channel: "inapp" as const, created_at: "x" };

function mount() {
  let poller!: ReturnType<typeof useAlertPoller>;
  const app = createApp({ setup() { poller = useAlertPoller(); return () => null; } });
  app.use(getActivePinia()!);
  app.mount(document.createElement("div"));
  return { poller, unmount: () => app.unmount() };
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
  vi.stubGlobal("Notification", undefined);
});

describe("useAlertPoller", () => {
  it("does nothing without the calendar permission", async () => {
    const auth = useAuthStore();
    auth.account = { id: 1, email_verified: true, permissions: ["chat.use"] } as never;
    const { poller, unmount } = mount();
    await nextTick();
    expect(client.unseenAlerts).not.toHaveBeenCalled();
    expect(poller.alerts.value).toEqual([]);
    unmount();
  });

  it("shows unseen alerts for a permitted account and dismisses them on the server", async () => {
    const auth = useAuthStore();
    auth.account = { id: 1, email_verified: true, permissions: ["calendar.use"] } as never;
    client.unseenAlerts.mockResolvedValue([ALERT]);
    client.markSeen.mockResolvedValue(undefined);
    const { poller, unmount } = mount();
    await vi.waitFor(() => expect(poller.alerts.value).toEqual([ALERT]));
    await poller.dismiss("a1");
    expect(client.markSeen).toHaveBeenCalledWith("a1");
    expect(poller.alerts.value).toEqual([]);
    unmount();
  });

  it("drops alerts for events that began long ago", async () => {
    const auth = useAuthStore();
    auth.account = { id: 1, email_verified: true, permissions: ["calendar.use"] } as never;
    client.unseenAlerts.mockResolvedValue([{ ...ALERT, start_utc: new Date(Date.now() - 3 * 3600_000).toISOString() }]);
    const { poller, unmount } = mount();
    await vi.waitFor(() => expect(client.unseenAlerts).toHaveBeenCalled());
    await nextTick();
    expect(poller.alerts.value).toEqual([]);
    unmount();
  });
});
```

If `auth.hasPermission` reads from `account.permissions`, the tests above hold; if the auth store computes it differently (read `src/stores/auth.ts` first), set the account fields it needs.

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/Ember/ember_web && npx vitest run src/features/calendar/composables/useAlertPoller.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the poller and the toasts**

Create `src/features/calendar/composables/useAlertPoller.ts`:

```ts
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useAuthStore } from "../../../stores/auth";
import { calendarClient, type CalendarAlert } from "../api/CalendarClient";

const INTERVAL_MS = 30_000;
// An alert for an event that began more than this long ago is no use any more.
const STALE_MS = 30 * 60_000;

/** Polls the in-app alert inbox while a signed-in account that may use the calendar has Ember open.
 * Each new alert also raises a desktop notification when the browser allows it. */
export function useAlertPoller() {
  const auth = useAuthStore();
  const alerts = ref<CalendarAlert[]>([]);
  const notified = new Set<string>();
  let timer: ReturnType<typeof setInterval> | undefined;
  let generation = 0;

  const active = computed(() => auth.account !== null && !auth.needsVerification && auth.hasPermission("calendar.use"));

  function notify(alert: CalendarAlert): void {
    if (notified.has(alert.id)) return;
    notified.add(alert.id);
    if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
    try {
      new Notification(alert.title, { body: `Starts at ${new Date(alert.start_utc).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`, tag: `ember-calendar-${alert.id}` });
    } catch {
      // The in-page toast still shows.
    }
  }

  async function poll(): Promise<void> {
    if (!active.value) return;
    const started = generation;
    try {
      const fresh = (await calendarClient.unseenAlerts()).filter((a) => Date.now() - new Date(a.start_utc).getTime() < STALE_MS);
      if (started !== generation) return;
      fresh.forEach(notify);
      alerts.value = fresh;
    } catch {
      // A failed poll is retried on the next tick; an alert is never lost, it stays unseen on the server.
    }
  }

  async function dismiss(id: string): Promise<void> {
    alerts.value = alerts.value.filter((a) => a.id !== id);
    await calendarClient.markSeen(id).catch(() => undefined);
  }

  const onVisible = () => { if (!document.hidden) void poll(); };

  watch(
    active,
    (on) => {
      generation += 1;
      clearInterval(timer);
      alerts.value = [];
      if (on) {
        void poll();
        timer = setInterval(() => void poll(), INTERVAL_MS);
      }
    },
    { immediate: true },
  );
  document.addEventListener("visibilitychange", onVisible);
  onBeforeUnmount(() => {
    clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisible);
  });

  return { alerts, dismiss, poll };
}
```

Create `src/features/calendar/components/AlertToasts.vue`:

```vue
<script setup lang="ts">
import { useAlertPoller } from "../composables/useAlertPoller";

const { alerts, dismiss } = useAlertPoller();

function startsAt(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
</script>

<template>
  <div v-if="alerts.length" class="toasts" role="region" aria-label="Calendar alerts">
    <article v-for="alert in alerts" :key="alert.id" class="toast" role="status">
      <div class="text">
        <strong>{{ alert.title }}</strong>
        <span>Starts at {{ startsAt(alert.start_utc) }}</span>
      </div>
      <RouterLink class="open" to="/calendar" @click="dismiss(alert.id)">Open</RouterLink>
      <button type="button" class="close" :aria-label="`Dismiss alert for ${alert.title}`" @click="dismiss(alert.id)">×</button>
    </article>
  </div>
</template>

<style scoped>
.toasts { position: fixed; z-index: 40; right: 16px; bottom: calc(var(--rail-height) + 12px); display: grid; gap: 8px; max-width: min(360px, calc(100vw - 32px)); }
@media (min-width: 768px) { .toasts { bottom: 16px; } }
.toast { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 10px; padding: 12px 14px; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--accent); border-radius: var(--radius-lg); }
.text { display: grid; min-width: 0; }
.text strong { overflow-wrap: anywhere; }
.text span { color: var(--muted); font-size: 0.85rem; }
.open { color: var(--accent); font-weight: 600; text-decoration: none; }
.close { min-width: 32px; min-height: 32px; color: var(--muted); background: transparent; border: 0; border-radius: var(--radius-md); font-size: 1.2rem; cursor: pointer; }
</style>
```

- [ ] **Step 4: Route, nav, App, push worker**

In `src/router/index.ts`, add before the `/settings` route:

```ts
    {
      path: "/calendar",
      name: "calendar",
      component: () => import("../features/calendar/CalendarView.vue"),
      meta: { permission: "calendar.use" },
    },
```

In `src/router/pages.ts`, add to `NAV_PAGES` before the Settings entry:

```ts
  {
    to: "/calendar",
    label: "Calendar",
    icon: ["M8 2v4", "M16 2v4", "M3 10h18", "M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"],
    description: "Your read-only schedule from ICS links, with alerts before events.",
    permission: "calendar.use",
  },
```

In `src/App.vue` add `import AlertToasts from "./features/calendar/components/AlertToasts.vue";` and, inside `<template>` right after `<PwaStatus ... />`, add `<AlertToasts />`.

In `vite.config.ts`, in the `workbox:` block add as the first key:

```ts
      // Push alerts: the worker's push and click handlers live in public/push-sw.js.
      importScripts: ['push-sw.js'],
```

Create `public/push-sw.js`:

```js
// Loaded into the app's service worker (workbox importScripts). Shows push alerts and opens the calendar on click.
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    // A plain-text payload falls back to the defaults below.
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Ember", {
      body: data.body || "",
      tag: "ember-calendar",
      data: { url: data.url || "/calendar" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/calendar";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if ("focus" in client) {
          if ("navigate" in client) client.navigate(url);
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});
```

- [ ] **Step 5: Run the whole web suite and the type check**

Run: `cd apps/Ember/ember_web && npx vitest run && npx vue-tsc -b`
Expected: PASS. Update any test that lists the pages or routes exactly (`src/router/index.test.ts`, `src/components/layout/NavRail.test.ts`, overview tests) by adding the Calendar entry; do not weaken their other assertions. `radiusScale.test.ts` must pass: every radius in the new files uses `var(--radius-*)`.

- [ ] **Step 6: Commit**

```bash
git add apps/Ember/ember_web
git commit -m "feat(calendar): route, nav entry, in-app alert toasts and push service worker handlers"
```

---

### Task 13: ember_admin channel switches

**Files:**
- Modify: `apps/Ember/ember_admin/src/api/SettingsClient.ts`
- Create: `apps/Ember/ember_admin/src/components/admin/CalendarChannelsPanel.vue`
- Create: `apps/Ember/ember_admin/src/components/admin/CalendarChannelsPanel.test.ts`
- Modify: the view that mounts `SettingsPanel` (find with `grep -rn "SettingsPanel" apps/Ember/ember_admin/src`)

**Interfaces:**
- Consumes: `settingsClient.get()`/`set(name, value)` (admin `SettingsClient.ts`).
- Produces: `AppSettings` gains `calendar_inapp`, `calendar_email`, `calendar_push` booleans; `CalendarChannelsPanel.vue` (no props, no emits).

- [ ] **Step 1: Write the failing test**

Create `src/components/admin/CalendarChannelsPanel.test.ts` (mirror the structure of `SettingsPanel.test.ts`: read it first and reuse its mounting helper, mocks and wait style):

```ts
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { settingsClient } from "../../api/SettingsClient";
import CalendarChannelsPanel from "./CalendarChannelsPanel.vue";

vi.mock("../../api/SettingsClient", () => ({ settingsClient: { get: vi.fn(), set: vi.fn() } }));
const client = vi.mocked(settingsClient);
const ALL_ON = { force_tool_approval: false, calendar_inapp: true, calendar_email: true, calendar_push: true };

beforeEach(() => {
  vi.clearAllMocks();
  client.get.mockResolvedValue(ALL_ON);
});

describe("CalendarChannelsPanel", () => {
  it("shows the three channels as stored and keeps Save disabled until something changes", async () => {
    const wrapper = mount(CalendarChannelsPanel);
    await flushPromises();
    const switches = wrapper.findAll<HTMLInputElement>("input[role=switch]");
    expect(switches.map((s) => s.element.checked)).toEqual([true, true, true]);
    expect(wrapper.get("button.save").attributes("disabled")).toBeDefined();
  });

  it("saves only the channels that changed, one request each, after Save", async () => {
    client.set.mockResolvedValue({});
    const wrapper = mount(CalendarChannelsPanel);
    await flushPromises();
    await wrapper.findAll("input[role=switch]")[2]!.setValue(false);
    expect(client.set).not.toHaveBeenCalled();
    await wrapper.get("button.save").trigger("click");
    await flushPromises();
    expect(client.set.mock.calls).toEqual([["calendar_push", false]]);
  });

  it("drops the draft on Cancel", async () => {
    const wrapper = mount(CalendarChannelsPanel);
    await flushPromises();
    await wrapper.findAll("input[role=switch]")[0]!.setValue(false);
    await wrapper.get("button.cancel").trigger("click");
    expect(wrapper.findAll<HTMLInputElement>("input[role=switch]")[0]!.element.checked).toBe(true);
  });

  it("keeps the draft and shows the error when saving fails", async () => {
    client.set.mockRejectedValue(new Error("nope"));
    const wrapper = mount(CalendarChannelsPanel);
    await flushPromises();
    await wrapper.findAll("input[role=switch]")[1]!.setValue(false);
    await wrapper.get("button.save").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("nope");
    expect(wrapper.findAll<HTMLInputElement>("input[role=switch]")[1]!.element.checked).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/Ember/ember_admin && npx vitest run src/components/admin/CalendarChannelsPanel.test.ts`
Expected: FAIL (component not found).

- [ ] **Step 3: Implement**

In `src/api/SettingsClient.ts` extend the interface:

```ts
export interface AppSettings {
  /** Every answer asks before each tool runs, and "allow for this chat" is not offered. */
  force_tool_approval: boolean;
  /** Calendar alert channels left on for everyone. */
  calendar_inapp: boolean;
  calendar_email: boolean;
  calendar_push: boolean;
}
```

Create `src/components/admin/CalendarChannelsPanel.vue` (a draft until Save, like `SettingsPanel`, because the switches reach every account; reuse its CSS classes by importing `./admin.css`):

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { settingsClient, type AppSettings } from "../../api/SettingsClient";
import { errorMessage } from "../../utils/errors";
import ToggleSwitch from "../ToggleSwitch.vue";
import "./admin.css";

type ChannelKey = "calendar_inapp" | "calendar_email" | "calendar_push";
const CHANNELS: { key: ChannelKey; label: string; help: string }[] = [
  { key: "calendar_inapp", label: "In-app alerts", help: "A banner and desktop notification while Ember is open." },
  { key: "calendar_email", label: "Email alerts", help: "Sent through the Email capability; it must be online." },
  { key: "calendar_push", label: "Push alerts", help: "Browser push, works with Ember closed. Needs HTTPS." },
];

const stored = ref<Pick<AppSettings, ChannelKey> | null>(null);
const draft = ref<Record<ChannelKey, boolean>>({ calendar_inapp: true, calendar_email: true, calendar_push: true });
const loadError = ref("");
const saveError = ref("");
const saving = ref(false);
const saved = ref(false);

const changed = computed(() => (stored.value ? CHANNELS.filter((c) => draft.value[c.key] !== stored.value![c.key]) : []));

function adopt(settings: AppSettings): void {
  stored.value = { calendar_inapp: settings.calendar_inapp, calendar_email: settings.calendar_email, calendar_push: settings.calendar_push };
  draft.value = { ...stored.value };
}

async function load(): Promise<void> {
  loadError.value = "";
  try {
    adopt(await settingsClient.get());
  } catch (err) {
    loadError.value = errorMessage(err);
  }
}

function cancel(): void {
  if (stored.value) draft.value = { ...stored.value };
  saveError.value = "";
}

async function save(): Promise<void> {
  saveError.value = "";
  saving.value = true;
  try {
    for (const channel of changed.value) await settingsClient.set(channel.key, draft.value[channel.key]);
    stored.value = { ...draft.value };
    saved.value = true;
  } catch (err) {
    saveError.value = errorMessage(err);
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="admin-panel">
    <p v-if="loadError" class="error">error: {{ loadError }}</p>
    <section class="card">
      <div class="head"><h3>Calendar alerts</h3></div>
      <p class="muted">Which ways calendar alerts may reach people. Switching one off stops it for every account.</p>
      <div v-for="channel in CHANNELS" :key="channel.key" class="row">
        <ToggleSwitch v-model="draft[channel.key]" :aria-label="channel.label" @change="saved = false">{{ channel.label }}</ToggleSwitch>
        <p class="muted">{{ channel.help }}</p>
      </div>
      <div v-if="changed.length" class="bar" role="status">
        <span>Unsaved: {{ changed.map((c) => c.label).join(", ") }}. Applies to every account.</span>
        <button type="button" class="cancel" :disabled="saving" @click="cancel">Cancel</button>
        <button type="button" class="save primary" :disabled="saving" :aria-busy="saving" @click="save">Save</button>
      </div>
      <button v-else type="button" class="save" disabled>Save</button>
      <p v-if="saveError" class="error" role="alert">error: {{ saveError }}</p>
      <p v-else-if="saved && !changed.length" class="muted" role="status">Saved.</p>
    </section>
  </div>
</template>
```

Before finishing: open admin's `ToggleSwitch.vue` and `SettingsPanel.vue`'s markup and match how the switch binds (`:checked` plus `@change`, versus `v-model`). If `ToggleSwitch` does not support `v-model`, use `:checked="draft[channel.key]" @change="draft[channel.key] = ($event.target as HTMLInputElement).checked; saved = false"`, and in the test set the draft with `setValue` as written (it dispatches `change`).

Mount `<CalendarChannelsPanel />` directly after `<SettingsPanel />` in the view that mounts it.

- [ ] **Step 4: Run checks**

Run: `cd apps/Ember/ember_admin && npx vitest run && npx vue-tsc -b`
Expected: PASS. Fix existing test fixtures that build an `AppSettings` object by adding the three calendar booleans. `radiusScale.test.ts` must pass.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_admin
git commit -m "feat(calendar): admin switches for the three alert channels"
```

---

### Task 14: End-to-end spec and full verification

**Files:**
- Modify: `apps/Ember/ember_web/e2e/fakeApi.ts`
- Create: `apps/Ember/ember_web/e2e/calendar.spec.ts`

**Interfaces:**
- Consumes: the `/api/calendar/*` contract from Task 9.
- Produces: `installFakeApi(page, { calendar: true })` adds permission `calendar.use`, a `calendar` state on `FakeApi` (`feeds`, `rules`, `alerts`), and handlers for every `/api/calendar` route plus `calendar_*` keys in `/api/settings`.

- [ ] **Step 1: Extend the fake API**

Read `e2e/fakeApi.ts` around `installFakeApi` (line ~247) and the `tickets` handlers (line ~354). Then:
- add `calendar?: boolean` to the options type and `...(options.calendar ? ["calendar.use"] : [])` to the account's permissions, as `tickets` does;
- add to the `FakeApi` interface and initial object: `calendar: { feeds: CalendarFeedStub[]; rules: RuleStub[]; alerts: AlertStub[] }` with empty arrays and one rule `{ id: "r1", channel: "inapp", lead_minutes: 15, enabled: true }`;
- in the existing `/api/settings` handler, add `calendar_inapp: true, calendar_email: true, calendar_push: false` to the reply;
- before the final `api.unexpected.push(...)` line add these handlers (names `json` and `route.fulfill` are the file's existing helpers):

```ts
    if (path.startsWith("/api/calendar")) {
      const cal = api.calendar;
      if (path === "/api/calendar/feeds" && method === "GET") return json(route, cal.feeds);
      if (path === "/api/calendar/feeds" && method === "POST") {
        const body = request.postDataJSON() as { name: string; color: string };
        const feed = { id: `f${cal.feeds.length + 1}`, name: body.name, color: body.color, enabled: true, last_fetch_at: null, last_error: null };
        cal.feeds.push(feed);
        return json(route, feed, 201);
      }
      const feedMatch = path.match(/^\/api\/calendar\/feeds\/([a-z0-9]+)$/);
      if (feedMatch && method === "DELETE") {
        cal.feeds = cal.feeds.filter((f) => f.id !== feedMatch[1]);
        return route.fulfill({ status: 204 });
      }
      if (path === "/api/calendar/events" && method === "GET") {
        const start = new Date(); start.setHours(10, 0, 0, 0);
        const end = new Date(start.getTime() + 3600_000);
        return json(route, {
          events: cal.feeds.length ? [{ uid: "e1", title: "Standup", start: start.toISOString(), end: end.toISOString(), all_day: false, location: "Room 1", description: "Agenda", sources: [{ name: cal.feeds[0]!.name, color: cal.feeds[0]!.color }] }] : [],
          errors: [],
        });
      }
      if (path === "/api/calendar/alarms" && method === "GET") return json(route, cal.rules);
      if (path === "/api/calendar/alarms" && method === "POST") {
        const body = request.postDataJSON() as { channel: string; lead_minutes: number };
        const rule = { id: `r${cal.rules.length + 1}`, channel: body.channel, lead_minutes: body.lead_minutes, enabled: true };
        cal.rules.push(rule);
        return json(route, rule, 201);
      }
      const ruleMatch = path.match(/^\/api\/calendar\/alarms\/([a-z0-9]+)$/);
      if (ruleMatch && method === "DELETE") {
        cal.rules = cal.rules.filter((r) => r.id !== ruleMatch[1]);
        return route.fulfill({ status: 204 });
      }
      if (path === "/api/calendar/prefs") return json(route, { timezone: "UTC", saved: true });
      if (path === "/api/calendar/alerts" && method === "GET") return json(route, cal.alerts);
      const seenMatch = path.match(/^\/api\/calendar\/alerts\/([a-z0-9-]+)\/seen$/);
      if (seenMatch && method === "POST") {
        cal.alerts = cal.alerts.filter((a) => a.id !== seenMatch[1]);
        return route.fulfill({ status: 204 });
      }
    }
```

If `json` takes no status parameter in this file, use `route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(...) })` for the two 201 replies.

- [ ] **Step 2: Write the spec**

Create `e2e/calendar.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test("add a calendar, see its event, add and remove an alert, and dismiss an in-app alert", async ({ page }) => {
  const api = await installFakeApi(page, { calendar: true });
  await logIn(page);
  await page.goto("/calendar");

  await expect(page.getByRole("heading", { name: "Calendar", level: 2 })).toBeVisible();
  await expect(page.getByText("No calendars yet")).toBeVisible();

  await page.getByLabel("Label").fill("Work");
  await page.getByLabel("ICS link").fill("https://example.com/a.ics");
  await page.getByRole("button", { name: "Add calendar" }).click();
  await expect(page.getByLabel("Name of calendar Work")).toBeVisible();
  await expect(page.locator(".fc-event", { hasText: "Standup" })).toBeVisible();

  await page.locator(".fc-event", { hasText: "Standup" }).click();
  const dialog = page.getByRole("dialog", { name: "Standup" });
  await expect(dialog.getByText("Room 1")).toBeVisible();
  await dialog.getByRole("button", { name: /close/i }).click();

  await page.getByLabel("Type").selectOption("email");
  await page.getByLabel("When").selectOption("30");
  await page.getByRole("button", { name: "Add alert" }).click();
  await expect(page.getByRole("list", { name: "Alert rules" }).getByText("Email")).toBeVisible();
  await page.getByRole("button", { name: "Remove Email alert 30 minutes before" }).click();
  await expect(page.getByRole("list", { name: "Alert rules" }).getByText("Email")).toHaveCount(0);

  api.calendar.alerts.push({ id: "a1", title: "Design review", start_utc: new Date(Date.now() + 600_000).toISOString(), channel: "inapp", created_at: "x" });
  await page.reload();
  const toast = page.getByRole("region", { name: "Calendar alerts" });
  await expect(toast.getByText("Design review")).toBeVisible();
  await toast.getByRole("button", { name: "Dismiss alert for Design review" }).click();
  await expect(toast).toHaveCount(0);

  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [1440, 768, 375]) {
      await page.setViewportSize({ width, height: 812 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
  }
  expect(api.unexpected).toEqual([]);
});

test("a member without calendar.use cannot open the page", async ({ page }) => {
  await installFakeApi(page);
  await logIn(page);
  await page.goto("/calendar");
  await expect(page).not.toHaveURL(/\/calendar/);
});
```

- [ ] **Step 3: Run the e2e spec and the full suites**

Run:
```bash
cd apps/Ember/ember_web && npx vue-tsc -b && npx vitest run && npx playwright test e2e/calendar.spec.ts
cd ../ember_admin && npx vue-tsc -b && npx vitest run
cd ../ember_api && ./.venv_ember_api/Scripts/python.exe -m pytest -q
```
Expected: everything passes. Fix selectors to the real accessible names if one differs (for example the dialog close button's name in `BaseModal`); do not loosen the assertions. Also run the full web e2e suite once (`npx playwright test`) to confirm no other spec now reports an unexpected request.

- [ ] **Step 4: Manual smoke (record in the PR description, do not skip)**

With ember_api and ember_web running (build + `vite preview` for push): add the Outlook link from `CalendarViewer/feeds.json`, confirm events appear, add an alert 5 minutes before a near event, and confirm the toast, the desktop notification and (with email configured and push turned on) the email and push alert. Confirm a second account cannot see the first account's calendars. Note anything not verified.

- [ ] **Step 5: Commit**

```bash
git add apps/Ember/ember_web/e2e
git commit -m "test(calendar): end-to-end spec and fake API routes"
```

---

## Self-review (run before handing off)

**Spec coverage**
- Goal, scope and out-of-scope list: Tasks 4, 9 (links only, private), no upload code anywhere.
- Backend tables/services/routes/scheduler rules: Tasks 2–9 (create-if-absent lock Task 4/8, grace/drop Task 8, 304/redirect/size/SSRF Task 3, email never retried Task 7/8, push 404/410 cleanup Task 7, all-day skipped Task 8, floating time in account zone Tasks 2/4, logs name feeds only Tasks 5/8/9).
- Configuration: admin switches Task 1 + Task 13; static block Task 1; VAPID Tasks 6/9; permission Task 1; config warning Task 9. Deviations from the spec, to record in the spec when this plan is approved: (a) the feed document has no `etag` (the etag lives in `FeedCache`, in memory); (b) the Config-issues page gets one warning (push needs HTTPS); the email-offline case surfaces as failed alerts and an Errors-log line, and the missing-secrets-key case cannot occur because the key is generated at startup.
- Frontend: Tasks 10–13 (FullCalendar, panels, event dialog, poller, push worker, admin panel). Account purge: Task 9.
- Testing section: pytest per service/route, vitest per util/store/poller/panel, Playwright light/dark and 1440/768/375.

**Placeholder scan:** no TBD/TODO steps. Three steps tell the executor to read an existing file and adapt to its exact shape (ToggleSwitch binding in Task 13, `BaseModal` close-button name in Task 14, the delete-account test helper in Task 9) because those shapes were not fully read; each states what to check and the fallback.

**Type consistency:** `CalendarStore` method names match across Tasks 4, 5, 7, 8, 9 (`feeds`, `rules`, `add_rule`, `update_rule`, `create_alert`, `unseen_alerts`, `push_subscriptions`, `remove_push_key`, `prune_alerts`, `zone`); `Recipient(uid, email)` is built in Task 9 and consumed in Tasks 7–8; `EventResult.errors` is `list[tuple[str, str]]` in Tasks 5 and 9; web `CalendarAlert.start_utc` matches `AlertOut.start_utc`.
