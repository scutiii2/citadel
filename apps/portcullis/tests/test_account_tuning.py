# apps/portcullis/tests/test_account_tuning.py
"""/api/account/tuning: the logged-in account's own response limits, kept by Stronghold."""

from __future__ import annotations

from tests.auth_helpers import requester, assertion

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
    assert requester(read)["username"] == "root" and requester(read)["sub"]


def test_stronghold_refusals_reach_the_browser_and_an_outage_is_a_502(client: TestClient, upstream: FakeUpstream) -> None:
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(400, json={"detail": "max_output_tokens cannot be above 2048"})
    over = client.put(URL, json={"max_output_tokens": 5000})
    assert over.status_code == 400 and "2048" in over.json()["detail"]

    upstream.handler = lambda r: httpx.Response(422, json={"detail": []})
    assert client.put(URL, json={"max_tool_rounds": 0}).status_code == 422

    upstream.handler = lambda r: httpx.Response(503, json={"detail": "down"})
    assert client.get(URL).status_code == 502
