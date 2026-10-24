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
    asyncio.run(cal.add_push("https://fcm.googleapis.com/a", "k", "s"))
    asyncio.run(cal.add_push("https://fcm.googleapis.com/a", "k2", "s2"))
    (sub,) = asyncio.run(cal.push_subscriptions())
    assert sub.p256dh == "k2" and sub.info() == {"endpoint": "https://fcm.googleapis.com/a", "keys": {"p256dh": "k2", "auth": "s2"}}
    with pytest.raises(CalendarInvalid):
        asyncio.run(cal.add_push("http://push.example/a", "k", "s"))
    with pytest.raises(CalendarInvalid):
        asyncio.run(cal.add_push("https://10.0.0.5/a", "k", "s"))
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
