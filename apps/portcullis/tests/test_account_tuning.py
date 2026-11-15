# apps/portcullis/tests/test_account_tuning.py
"""/api/account/tuning: the logged-in account's own response limits, kept by Stronghold."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from tests.conftest import FakeUpstream
from tests.test_registration import as_admin

URL = "/api/account/tuning"


def test_needs_login(client: TestClient, upstream: FakeUpstream) -> None:
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={}).status_code == 401
    assert client.delete(URL).status_code == 401
    assert not upstream.requests


def test_read_save_and_reset_go_to_stronghold(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(204) if r.method == "DELETE" else httpx.Response(200, json={"limits": {}})
    upstream.requests.clear()

    assert client.get(URL).status_code == 200
    assert client.put(URL, json={"max_tool_rounds": 4}).status_code == 200
    assert client.delete(URL).status_code == 204

    read, save, reset = upstream.requests
    assert [(r.method, r.url.path) for r in (read, save, reset)] == [("GET", "/tuning/limits"), ("PUT", "/tuning/limits"), ("DELETE", "/tuning/limits")]
    assert json.loads(save.content) == {"max_tool_rounds": 4}
    assert read.headers["x-requester-username"] == "root" and read.headers["x-requester-uid"]


def test_stronghold_refusals_reach_the_browser_and_an_outage_is_a_502(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(400, json={"detail": "max_output_tokens cannot be above 2048"})
    over = client.put(URL, json={"max_output_tokens": 5000})
    assert over.status_code == 400 and "2048" in over.json()["detail"]

    upstream.handler = lambda r: httpx.Response(422, json={"detail": []})
    assert client.put(URL, json={"max_tool_rounds": 0}).status_code == 422

    upstream.handler = lambda r: httpx.Response(503, json={"detail": "down"})
    assert client.get(URL).status_code == 502


def test_saved_limits_reach_the_chat_turn(client, upstream, agent):
    from tests.test_turns import events, new_id, start
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(200, json={"max_tool_rounds": 4, "max_output_tokens": True, "other": 1}) \
        if r.url.path == "/tuning/limits/own" else httpx.Response(200, json={})
    chat_id = new_id()

    assert start(client, chat_id).status_code == 202
    events(client, chat_id)

    assert agent.asks[-1]["limits"] == {"max_tool_rounds": 4}  # only the two known fields, only whole numbers
    assert any(r.url.path == "/tuning/limits/own" and r.method == "GET" for r in upstream.requests)


def test_a_stronghold_failure_keeps_the_turn_running_without_limits(client, upstream, agent):
    from tests.test_turns import events, new_id, start
    as_admin(client)

    for handler in (lambda r: httpx.Response(503, json={}), lambda r: httpx.Response(200, content=b"not json"),
                    lambda r: httpx.Response(200, json=["list"]), lambda r: httpx.Response(404, json={})):
        upstream.handler = handler
        chat_id = new_id()
        assert start(client, chat_id).status_code == 202
        events(client, chat_id)
        assert (agent.asks[-1]["limits"] or {}) == {}
