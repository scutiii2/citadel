"""/account-agents: the agents an account switched off, and what the store keeps."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from src.agents.accounts import COLLECTION, AccountAgentService, blocked_names

URL = "/account-agents"


def test_every_agent_is_on_until_the_account_switches_one_off(client: TestClient) -> None:
    assert client.get(URL).json() == {"disabled": []}


def test_a_switched_off_agent_is_listed_and_back_on_removes_it(client: TestClient) -> None:
    assert client.put(f"{URL}/claude-agent", json={"enabled": False}).json() == {"disabled": ["claude-agent"]}
    assert client.put(f"{URL}/claude-agent", json={"enabled": False}).json() == {"disabled": ["claude-agent"]}
    assert client.get(URL).json() == {"disabled": ["claude-agent"]}

    assert client.put(f"{URL}/claude-agent", json={"enabled": True}).json() == {"disabled": []}


def test_the_list_is_private_to_the_account(client: TestClient) -> None:
    client.put(f"{URL}/claude-agent", json={"enabled": False})

    assert client.get(URL, headers={"X-Requester-Uid": "u-2"}).json() == {"disabled": []}


def test_an_agent_id_must_look_like_one(client: TestClient) -> None:
    assert client.put(f"{URL}/not an id!", json={"enabled": False}).status_code == 422
    assert client.put(f"{URL}/{'x' * 65}", json={"enabled": False}).status_code == 422


def test_the_requester_is_required(client: TestClient) -> None:
    assert client.get(URL, headers={"X-Requester-Uid": ""}).status_code == 400


def test_purge_forgets_the_list(client: TestClient) -> None:
    client.put(f"{URL}/claude-agent", json={"enabled": False})

    assert client.delete(f"{URL}/accounts/u-1").status_code == 204
    assert client.get(URL).json() == {"disabled": []}


def test_storage_down_is_a_503_not_an_empty_list(client: TestClient, db_gateway, monkeypatch) -> None:
    from src.document_store import DbGatewayUnavailable

    async def down(*args, **kwargs):
        raise DbGatewayUnavailable("down")

    monkeypatch.setattr(db_gateway, "get", down)

    assert client.get(URL).status_code == 503


def test_blocked_names_are_the_tool_filter_entries() -> None:
    assert blocked_names(["planner"]) == ["agent:planner"]


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
