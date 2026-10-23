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
