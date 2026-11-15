"""/tuning: an account's own response limits, capped by what Legion's tuning allows."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from src.document_store import DbGatewayUnavailable
from tests.conftest import FakeDbGateway
from tests.helpers import login, uid_of

URL = "/tuning/limits"
VIEW = {"defaults": {}, "overrides": {}, "effective": {"token_limits": {"default": {"max_output_tokens": 2048, "max_tool_rounds": 15}}}}
NONE = {"max_output_tokens": None, "max_tool_rounds": None}


def legion_up(legion) -> None:
    legion.handler = lambda request: httpx.Response(200, json=VIEW)


def test_every_route_needs_the_requester(client: TestClient) -> None:
    anonymous = {"X-Requester-Uid": ""}
    assert client.get(URL, headers=anonymous).status_code == 400
    assert client.get(f"{URL}/own", headers=anonymous).status_code == 400
    assert client.put(URL, json={}, headers=anonymous).status_code == 400
    assert client.delete(URL, headers=anonymous).status_code == 400


def test_default_is_unset_with_the_admin_values_as_ceiling(client: TestClient, legion) -> None:
    legion_up(legion)

    assert client.get(URL).json() == {"limits": NONE, "ceiling": {"max_output_tokens": 2048, "max_tool_rounds": 15}}
    sent = legion.requests[-1]
    assert sent.url.host == "agent-a.internal" and sent.url.path == "/agents/tuning"  # the entry agent's own server
    assert sent.headers["x-requester-username"] == "ana" and sent.headers["x-internal-token"] == "shared-test-token"


def test_save_read_back_and_clear_one(client: TestClient, legion) -> None:
    legion_up(legion)

    saved = client.put(URL, json={"max_output_tokens": 500, "max_tool_rounds": 4})
    assert saved.status_code == 200
    assert saved.json()["limits"] == {"max_output_tokens": 500, "max_tool_rounds": 4}
    cleared = client.put(URL, json={"max_output_tokens": None, "max_tool_rounds": 4})
    assert cleared.json()["limits"] == {"max_output_tokens": None, "max_tool_rounds": 4}
    assert client.get(f"{URL}/own").json() == {"max_tool_rounds": 4}


def test_a_value_above_the_admin_ceiling_is_refused(client: TestClient, legion) -> None:
    legion_up(legion)

    over = client.put(URL, json={"max_output_tokens": 5000, "max_tool_rounds": 4})

    assert over.status_code == 400 and "2048" in over.json()["detail"]
    assert client.get(URL).json()["limits"]["max_tool_rounds"] is None


def test_out_of_range_is_a_422(client: TestClient, legion) -> None:
    legion_up(legion)
    assert client.put(URL, json={"max_tool_rounds": 0}).status_code == 422
    assert client.put(URL, json={"max_tool_rounds": 101}).status_code == 422
    assert client.put(URL, json={"max_output_tokens": 200_001}).status_code == 422


def test_legion_down_still_reads_but_cannot_save(client: TestClient, legion) -> None:
    legion_up(legion)
    client.put(URL, json={"max_tool_rounds": 4})

    legion.handler = lambda request: httpx.Response(503, json={"error": "down"})
    body = client.get(URL).json()
    assert body["limits"]["max_tool_rounds"] == 4 and body["ceiling"] == NONE
    assert client.put(URL, json={"max_tool_rounds": 3}).status_code == 502

    def unreachable(request):
        raise httpx.ConnectError("down")

    legion.handler = unreachable
    assert client.put(URL, json={"max_tool_rounds": 3}).status_code == 502
    legion.handler = lambda request: httpx.Response(200, json={"effective": {}})  # not the shape we need
    assert client.put(URL, json={"max_tool_rounds": 3}).status_code == 502


def test_no_running_agent_cannot_save(client: TestClient, tmp_path) -> None:
    (tmp_path / "config_agents.json").write_text('{"agents": []}', encoding="utf-8")

    assert client.put(URL, json={"max_tool_rounds": 3}).status_code == 502
    assert client.get(URL).json()["ceiling"] == NONE


def test_delete_clears_everything(client: TestClient, legion) -> None:
    legion_up(legion)
    client.put(URL, json={"max_tool_rounds": 4})

    assert client.delete(URL).status_code == 204

    assert client.get(URL).json()["limits"] == NONE


def test_limits_are_private_per_account(client: TestClient, legion) -> None:
    legion_up(legion)
    login(client, "alice")
    client.put(URL, json={"max_tool_rounds": 4})
    login(client, "bob")

    assert client.get(URL).json()["limits"] == NONE
    assert client.get(f"{URL}/own").json() == {}
    login(client, "alice")
    assert client.get(f"{URL}/own").json() == {"max_tool_rounds": 4}


def test_storage_trouble_reads_as_no_limits_and_blocks_writes(client: TestClient, db_gateway: FakeDbGateway, legion, monkeypatch) -> None:
    legion_up(legion)

    async def broken(*args, **kwargs):
        raise DbGatewayUnavailable("down")

    monkeypatch.setattr(db_gateway, "get", broken)
    monkeypatch.setattr(db_gateway, "put", broken)
    monkeypatch.setattr(db_gateway, "delete", broken)

    assert client.get(f"{URL}/own").json() == {}
    assert client.get(URL).json()["limits"] == NONE
    assert client.put(URL, json={"max_tool_rounds": 3}).status_code == 503
    assert client.delete(URL).status_code == 503


def test_stored_junk_is_ignored(client: TestClient, db_gateway: FakeDbGateway) -> None:
    db_gateway.records[("tuning_limits", "u-1")] = {"max_output_tokens": True, "max_tool_rounds": "9", "other": 5}

    assert client.get(f"{URL}/own").json() == {}


def test_purging_an_account_removes_only_its_limits(client: TestClient, db_gateway: FakeDbGateway, legion) -> None:
    legion_up(legion)
    login(client, "alice")
    client.put(URL, json={"max_tool_rounds": 4})
    login(client, "bob")
    client.put(URL, json={"max_tool_rounds": 5})

    assert client.delete(f"/tuning/accounts/{uid_of('alice')}").status_code == 204

    assert [doc["max_tool_rounds"] for doc in db_gateway.records.values()] == [5]
    assert client.delete("/tuning/accounts/has%20space").status_code == 422
