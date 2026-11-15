from __future__ import annotations

import asyncio
import json
import types
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from pywebpush import WebPushException

from src.calendar.settings import CalendarSettings
from src.calendar.channels import (
    AlertMessage, ChannelError, EmailChannel, InAppChannel, PushChannel, Recipient,
)
from src.calendar.store import CalendarStore
from src.secret_box import SecretBox
from src.keys import load_keys
from tests.conftest import FakeDbGateway, FakePlatform

WHO = Recipient("u1", "ada@example.com")
MESSAGE = AlertMessage("Standup\nBCC: x", datetime(2026, 10, 26, 13, tzinfo=timezone.utc), 15, ("Work",))


def store() -> CalendarStore:
    return CalendarStore(FakeDbGateway(), "u1", SecretBox(Fernet.generate_key().decode("ascii")), CalendarSettings())


def test_in_app_sends_nothing() -> None:
    assert asyncio.run(InAppChannel().send(MESSAGE, WHO, store())) is None


def test_email_goes_to_the_recipient_with_a_single_line_subject() -> None:
    platform = FakePlatform()
    cal = store()
    asyncio.run(cal.set_timezone("America/New_York"))
    asyncio.run(EmailChannel(platform.notify).send(MESSAGE, WHO, cal))
    (to, subject, body), = platform.sent
    assert to == "u1"  # the account, not an address: Portcullis looks the address up
    assert subject == "Starting in 15 min: Standup BCC: x" and "\n" not in subject
    assert "09:00" in body and "America/New_York" in body and "Work" in body


def test_email_failure_propagates_so_the_scheduler_can_mark_it() -> None:
    async def failing(uid, subject, body):
        raise RuntimeError("smtp down")

    with pytest.raises(RuntimeError):
        asyncio.run(EmailChannel(failing).send(MESSAGE, WHO, store()))


def push_channel(sent: list, raises: Exception | None = None) -> PushChannel:
    keys = load_keys(_env())

    def sender(subscription, payload, vapid, claims):
        sent.append((subscription["endpoint"], json.loads(payload), claims))
        if raises:
            raise raises

    return PushChannel(keys.vapid_private, "mailto:admin@example.com", sender)


def _env():
    import tempfile
    from pathlib import Path
    return Path(tempfile.mkdtemp()) / ".env"


def test_push_reaches_every_subscription() -> None:
    cal, sent = store(), []
    asyncio.run(cal.add_push("https://fcm.googleapis.com/a", "k", "s"))
    asyncio.run(cal.add_push("https://fcm.googleapis.com/b", "k", "s"))
    asyncio.run(push_channel(sent).send(MESSAGE, WHO, cal))
    assert sorted(e for e, _, _ in sent) == ["https://fcm.googleapis.com/a", "https://fcm.googleapis.com/b"]
    _, payload, claims = sent[0]
    assert payload == {"title": "Standup BCC: x", "body": "Starts in 15 min", "url": "/calendar"}
    assert claims == {"sub": "mailto:admin@example.com"}


def test_push_without_a_subscription_is_a_channel_error() -> None:
    with pytest.raises(ChannelError):
        asyncio.run(push_channel([]).send(MESSAGE, WHO, store()))


def test_a_gone_subscription_is_removed() -> None:
    cal, sent = store(), []
    asyncio.run(cal.add_push("https://fcm.googleapis.com/a", "k", "s"))
    gone = WebPushException("gone", response=types.SimpleNamespace(status_code=410))
    with pytest.raises(ChannelError):
        asyncio.run(push_channel(sent, gone).send(MESSAGE, WHO, cal))
    assert asyncio.run(cal.push_subscriptions()) == []
