"""Agents an account switched off: what the route stores and what reaches the agent."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from src.services.account_agent_service import COLLECTION, AccountAgentService

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


def stored(db_gateway, disabled: list[str]) -> AccountAgentService:
    db_gateway.records[(COLLECTION, "u1")] = {"owner": "u1", "disabled": disabled}
    return AccountAgentService(db_gateway, "u1")


def test_retired_agents_are_left_out_of_the_read_and_dropped_on_the_next_write(db_gateway) -> None:
    service = stored(db_gateway, ["planner", "reviewer", "scheduler"])
    known = {"reviewer", "server-ops"}

    assert asyncio.run(service.disabled(known)) == ["reviewer"]
    assert asyncio.run(service.set_enabled("server-ops", False, known)) == ["reviewer", "server-ops"]
    assert db_gateway.records[(COLLECTION, "u1")]["disabled"] == ["reviewer", "server-ops"]


def test_a_no_op_toggle_still_cleans_retired_ids(db_gateway) -> None:
    service = stored(db_gateway, ["planner", "reviewer"])

    assert asyncio.run(service.set_enabled("reviewer", False, {"reviewer"})) == ["reviewer"]
    assert db_gateway.records[(COLLECTION, "u1")]["disabled"] == ["reviewer"]


def test_nothing_is_pruned_when_the_roster_is_unknown(db_gateway) -> None:
    service = stored(db_gateway, ["planner", "reviewer"])

    assert asyncio.run(service.disabled(set())) == ["planner", "reviewer"]
    assert asyncio.run(service.set_enabled("reviewer", False, set())) == ["planner", "reviewer"]
    assert asyncio.run(service.disabled()) == ["planner", "reviewer"]
