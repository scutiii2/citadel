"""UsageClient: the check before and the record after every agent call, answered by Stronghold."""

import json

from tests.auth_helpers import requester, assertion
import logging
from datetime import datetime

import httpx
import pytest

from src.services.stronghold_forwarder import StrongholdForwarder
from src.services.usage_client import UsageClient, UsageUnavailable
from src.services.usage_rows import stored_rows
from src.config import UsageSettings
from tests.test_registration import as_admin

ACCOUNT = type("Who", (), {"uid": "u-1", "username": "ana", "email": "ana@example.com"})()
RESULT = {"agent_usage": [
    {"agent_id": "main", "agent_label": "Main", "provider_id": "claude", "model": "m", "input_tokens": 6, "output_tokens": 4,
     "total_tokens": 10, "started_at": "2026-03-15T10:00:00Z", "context_breakdown": {"system": 1}},
    {"agent_id": "calc", "provider_id": "openai", "total_tokens": 5, "delegated_by": "main"},
    {"agent_id": "idle", "total_tokens": 0},
]}


def forwarder(handler):
    return StrongholdForwarder(httpx.AsyncClient(transport=httpx.MockTransport(handler)), "http://stronghold.test", None)


def run(coro):
    import asyncio

    return asyncio.run(coro)


def test_stored_rows_drop_display_only_keys_and_write_times_as_text():
    rows = stored_rows(RESULT)

    assert [r["agent"] for r in rows] == ["main", "calc"]
    assert rows[0]["started_at"] == "2026-03-15T10:00:00" and rows[1]["started_at"] is None
    assert not any("agent_label" in r or "context_breakdown" in r for r in rows)
    json.dumps(rows)  # ready to send


def test_check_returns_none_when_under_the_limit_and_the_block_when_over():
    answers = iter([{"block": None}, {"block": {"reason": "weekly token limit reached", "reset_at": "2026-03-20T10:00:00"}}])
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, requester(request)["sub"], assertion(request)["iss"]))
        return httpx.Response(200, json=next(answers))

    usage = UsageClient(forwarder(handler), ACCOUNT)

    assert run(usage.check()) is None
    block = run(usage.check())
    assert (block.reason, block.reset_at) == ("weekly token limit reached", datetime(2026, 3, 20, 10))
    assert seen == [("POST", "/usage/check", "u-1", "portcullis")] * 2


@pytest.mark.parametrize("answer", [
    lambda request: httpx.Response(503, json={"detail": "Storage is unavailable"}),
    lambda request: httpx.Response(404, json={"detail": "Not found"}),
    lambda request: httpx.Response(200, text="not json"),
    lambda request: httpx.Response(200, json={}),
    lambda request: (_ for _ in ()).throw(httpx.ConnectError("offline")),
])
def test_a_check_that_cannot_be_answered_is_refused(answer):
    with pytest.raises(UsageUnavailable):
        run(UsageClient(forwarder(answer), ACCOUNT).check())


def test_record_sends_the_turn_and_its_rows():
    sent = []

    def handler(request):
        sent.append((request.url.path, json.loads(request.content)))
        return httpx.Response(201, json={"total": 15})

    run(UsageClient(forwarder(handler), ACCOUNT).record("turn-1", "chat", "chat-1", RESULT))

    path, body = sent[0]
    assert path == "/usage/records"
    assert (body["turn_id"], body["kind"], body["chat_id"]) == ("turn-1", "chat", "chat-1")
    assert [r["total_tokens"] for r in body["rows"]] == [10, 5]


def test_record_with_nothing_spent_sends_nothing():
    def handler(request):
        raise AssertionError("no call expected")

    run(UsageClient(forwarder(handler), ACCOUNT).record("t", "chat", None, {"agent_usage": [], "total_tokens": 0}))


@pytest.mark.parametrize("answer", [
    lambda request: httpx.Response(503, json={"detail": "down"}),
    lambda request: httpx.Response(422, json={"detail": "bad"}),
    lambda request: (_ for _ in ()).throw(httpx.ConnectError("offline")),
])
def test_a_record_that_cannot_be_stored_is_logged_and_never_raises(answer, caplog):
    caplog.set_level(logging.WARNING)

    run(UsageClient(forwarder(answer), ACCOUNT).record("turn-1", "chat", None, RESULT))

    assert "recording usage of chat turn-1 failed" in caplog.text
    assert "u-1" not in caplog.text


# --- through the app -----------------------------------------------------------------


def test_the_token_limits_are_no_longer_settings_of_portcullis():
    assert not hasattr(UsageSettings(), "six_hour_token_limit")
