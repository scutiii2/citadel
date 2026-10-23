"""Agents an account switched off: what the route stores and what reaches the agent."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import FakeAgent
from tests.test_registration import as_admin
from tests.test_turns import events, new_id, start

URL = "/api/account-agents"


def test_every_agent_is_on_until_the_account_switches_one_off(client: TestClient, agent: FakeAgent) -> None:
    as_admin(client)
    assert client.get(URL).json() == {"disabled": []}

    chat_id = new_id()
    start(client, chat_id, "hi")
    events(client, chat_id)

    assert agent.asks[0]["disabled_tools"] == []


def test_a_switched_off_agent_is_passed_to_the_agent_as_a_filter_entry(client: TestClient, agent: FakeAgent) -> None:
    as_admin(client)
    chat_id = new_id()

    assert client.put(f"{URL}/planner", json={"enabled": False}).json() == {"disabled": ["planner"]}
    assert client.put(f"{URL}/planner", json={"enabled": False}).json() == {"disabled": ["planner"]}
    start(client, chat_id, "hi")
    events(client, chat_id)

    assert agent.asks[0]["disabled_tools"] == ["agent:planner"]


def test_switching_an_agent_back_on_removes_it(client: TestClient, agent: FakeAgent) -> None:
    as_admin(client)
    client.put(f"{URL}/planner", json={"enabled": False})

    assert client.put(f"{URL}/planner", json={"enabled": True}).json() == {"disabled": []}
    assert client.get(URL).json() == {"disabled": []}


def test_the_browser_can_no_longer_name_tools_to_switch_off(client: TestClient, agent: FakeAgent) -> None:
    as_admin(client)
    chat_id = new_id()

    start(client, chat_id, "hi", disabled_tools=["tool_calc"])
    events(client, chat_id)

    assert agent.asks[0]["disabled_tools"] == []


def test_an_agent_id_must_look_like_one(client: TestClient) -> None:
    as_admin(client)

    assert client.put(f"{URL}/not an id!", json={"enabled": False}).status_code == 422
    assert client.put(f"{URL}/{'x' * 65}", json={"enabled": False}).status_code == 422


def test_login_is_required(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
