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
    body = {"endpoint": "https://fcm.googleapis.com/a", "keys": {"p256dh": "k", "auth": "s"}}
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
