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
