"""/api/account-agents: Portcullis checks the login and passes the call to Stronghold, which stores the list;
a turn leaves the switched-off agents out."""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from tests.conftest import FakeAgent
from tests.test_registration import as_admin
from tests.test_turns import events, new_id, start

URL = "/api/account-agents"


def test_login_is_required(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.put(f"{URL}/planner", json={"enabled": False}).status_code == 401


def test_the_calls_go_to_stronghold_with_their_body_and_status(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.agents_fake = False
    upstream.handler = lambda request: httpx.Response(
        200, json={"disabled": ["planner"], "path": request.url.path, "body": json.loads(request.content or b"null")})

    read = client.get(URL).json()
    wrote = client.put(f"{URL}/planner", json={"enabled": False}).json()

    assert (read["path"], read["body"]) == ("/account-agents", None)
    assert (wrote["path"], wrote["body"]) == ("/account-agents/planner", {"enabled": False})


def test_an_agent_id_must_look_like_one(client: TestClient, upstream) -> None:
    as_admin(client)
    seen = len(upstream.requests)

    assert client.put(f"{URL}/not an id!", json={"enabled": False}).status_code == 422
    assert client.put(f"{URL}/{'x' * 65}", json={"enabled": False}).status_code == 422
    assert len(upstream.requests) == seen


def test_the_change_is_logged_only_when_stronghold_accepted_it(client: TestClient, upstream) -> None:
    as_admin(client)
    me = client.get("/api/auth/me").json()["id"]
    upstream.agents_fake = False
    upstream.handler = lambda request: httpx.Response(409, json={"detail": "Too many agents switched off on this account"})
    assert client.put(f"{URL}/planner", json={"enabled": False}).status_code == 409
    upstream.handler = lambda request: httpx.Response(200, json={"disabled": ["planner"]})
    assert client.put(f"{URL}/planner", json={"enabled": False}).status_code == 200
    assert client.put(f"{URL}/planner", json={"enabled": True}).status_code == 200

    logged = [e["message"] for e in client.get("/api/logs/action", params={"actor": me}).json()]

    assert logged[:2] == ["Enabled agent 'planner'", "Disabled agent 'planner'"]
    assert logged.count("Disabled agent 'planner'") == 1


def test_stronghold_down_is_a_502(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.agents_fake = False
    upstream.unreachable = True

    assert client.get(URL).status_code == 502


def test_every_agent_is_on_until_the_account_switches_one_off(client: TestClient, agent: FakeAgent) -> None:
    as_admin(client)
    chat_id = new_id()

    start(client, chat_id, "hi")
    events(client, chat_id)

    assert agent.asks[0]["disabled_tools"] == []


def test_a_switched_off_agent_is_passed_to_the_agent_as_a_filter_entry(client: TestClient, agent: FakeAgent, upstream) -> None:
    as_admin(client)
    upstream.disabled_agents = ["planner"]
    chat_id = new_id()

    start(client, chat_id, "hi")
    events(client, chat_id)

    assert agent.asks[0]["disabled_tools"] == ["agent:planner"]


def test_the_browser_can_no_longer_name_tools_to_switch_off(client: TestClient, agent: FakeAgent) -> None:
    as_admin(client)
    chat_id = new_id()

    start(client, chat_id, "hi", disabled_tools=["tool_calc"])
    events(client, chat_id)

    assert agent.asks[0]["disabled_tools"] == []


def test_without_the_list_the_turn_is_refused_rather_than_offering_every_agent(client: TestClient, upstream) -> None:
    as_admin(client)
    upstream.agents_status = 503

    assert start(client, new_id(), "hi").status_code == 503
