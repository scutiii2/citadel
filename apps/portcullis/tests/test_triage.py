"""/api/triage: Portcullis checks the login and chat.use; Stronghold asks the agents and counts the usage."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from tests.conftest import FakeEmailSender
from tests.test_account_uid import uids
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

TITLES = "/api/triage/titles"
ASK = "/api/triage/ask"
YES_NO = {"kind": "yes_no", "text": "SQLite database is locked", "question": "Is there a problem?"}
DESCRIPTIONS = {"descriptions": ["SQL and storage", "Connections"]}


def test_needs_login(client: TestClient, upstream) -> None:
    assert client.post(TITLES, json=DESCRIPTIONS).status_code == 401
    assert client.post(ASK, json=YES_NO).status_code == 401
    assert upstream.requests == []


def test_unverified_account_is_refused(client: TestClient, email: FakeEmailSender, upstream) -> None:
    make_member(client, email, "alice", verify=False)
    login(client, "alice")
    upstream.requests.clear()

    assert client.post(ASK, json=YES_NO).status_code == 403
    assert client.post(TITLES, json=DESCRIPTIONS).status_code == 403
    assert upstream.requests == []


def test_both_routes_go_to_stronghold_as_the_signed_in_account(client: TestClient, upstream) -> None:
    upstream.handler = lambda request: httpx.Response(200, json={"path": request.url.path})
    as_admin(client)
    uid = uids(client)["root"]

    assert client.post(TITLES, json=DESCRIPTIONS).json() == {"path": "/triage/titles"}
    assert client.post(ASK, json={**YES_NO, "trace": True}).json() == {"path": "/triage/ask"}

    assert all(request.headers["x-requester-uid"] == uid for request in upstream.requests)
    assert json.loads(upstream.requests[1].content) == {**YES_NO, "trace": True}


def test_a_token_limit_answer_keeps_its_status_and_retry_after(client: TestClient, upstream) -> None:
    upstream.handler = lambda request: httpx.Response(
        429, json={"detail": "You've reached your 6-hour token limit. It frees up in about 59 min."},
        headers={"Retry-After": "3540"})
    as_admin(client)

    limited = client.post(ASK, json=YES_NO)

    assert limited.status_code == 429 and "6-hour token limit" in limited.json()["detail"]
    assert limited.headers["Retry-After"] == "3540"


def test_other_refusals_and_a_down_stronghold_pass_through_as_they_are(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(422, json={"detail": "Laya could not read the complete input"})
    assert client.post(ASK, json=YES_NO).status_code == 422
    upstream.handler = lambda request: httpx.Response(503, json={"detail": "The Triage Assistant is unavailable"})
    assert client.post(ASK, json=YES_NO).status_code == 502  # Stronghold answered 5xx: the gateway says so
    upstream.unreachable = True
    assert client.post(TITLES, json=DESCRIPTIONS).json()["detail"] == "Stronghold is unavailable"
