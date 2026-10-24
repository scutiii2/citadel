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
