# apps/Ember/ember_api/tests/test_account_tuning.py
"""/api/account/tuning: the logged-in account's own response limits."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from tests.conftest import FakeUpstream
from tests.test_registration import as_admin

URL = "/api/account/tuning"
VIEW = {"defaults": {}, "overrides": {}, "effective": {"token_limits": {"default": {"max_output_tokens": 2048, "max_tool_rounds": 15}}}}


def legion_up(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=VIEW)


def test_needs_login(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={}).status_code == 401


def test_default_is_unset_with_the_admin_values_as_ceiling(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = legion_up
    as_admin(client)
    assert client.get(URL).json() == {
        "limits": {"max_output_tokens": None, "max_tool_rounds": None},
        "ceiling": {"max_output_tokens": 2048, "max_tool_rounds": 15},
    }


def test_save_read_back_and_clear_one(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = legion_up
    as_admin(client)
    saved = client.put(URL, json={"max_output_tokens": 500, "max_tool_rounds": 4})
    assert saved.status_code == 200
    assert saved.json()["limits"] == {"max_output_tokens": 500, "max_tool_rounds": 4}
    cleared = client.put(URL, json={"max_output_tokens": None, "max_tool_rounds": 4})
    assert cleared.json()["limits"] == {"max_output_tokens": None, "max_tool_rounds": 4}


def test_value_above_the_admin_ceiling_is_refused(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = legion_up
    as_admin(client)
    over = client.put(URL, json={"max_output_tokens": 5000, "max_tool_rounds": 4})
    assert over.status_code == 400
    assert "2048" in over.json()["detail"]
    assert client.get(URL).json()["limits"]["max_tool_rounds"] is None


def test_out_of_range_is_a_422(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = legion_up
    as_admin(client)
    assert client.put(URL, json={"max_tool_rounds": 0}).status_code == 422
    assert client.put(URL, json={"max_tool_rounds": 101}).status_code == 422


def test_legion_down_still_reads_but_cannot_save(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = legion_up
    as_admin(client)
    client.put(URL, json={"max_tool_rounds": 4})
    upstream.handler = lambda request: httpx.Response(503, json={"error": "down"})
    body = client.get(URL).json()
    assert body["limits"]["max_tool_rounds"] == 4
    assert body["ceiling"] == {"max_output_tokens": None, "max_tool_rounds": None}
    assert client.put(URL, json={"max_tool_rounds": 3}).status_code == 502


def test_delete_clears_everything(client: TestClient, upstream: FakeUpstream) -> None:
    upstream.handler = legion_up
    as_admin(client)
    client.put(URL, json={"max_tool_rounds": 4})
    assert client.delete(URL).status_code == 204
    assert client.get(URL).json()["limits"] == {"max_output_tokens": None, "max_tool_rounds": None}


def test_saved_limits_reach_the_chat_turn(client, upstream, agent):
    from tests.test_turns import events, new_id, start
    upstream.handler = legion_up
    as_admin(client)
    assert client.put(URL, json={"max_tool_rounds": 4}).status_code == 200
    chat_id = new_id()
    assert start(client, chat_id).status_code == 202
    events(client, chat_id)
    assert agent.asks[-1]["limits"] == {"max_tool_rounds": 4}


def test_only_tuning_storage_failure_keeps_the_turn_running(client, db_gateway, agent, monkeypatch):
    from src.services.db_gateway import DbGatewayUnavailable
    from tests.test_turns import events, new_id, start
    as_admin(client)
    original = db_gateway.get

    async def get(collection, key):
        if collection == "tuning_limits":
            raise DbGatewayUnavailable("tuning limits unavailable")
        return await original(collection, key)

    monkeypatch.setattr(db_gateway, "get", get)
    chat_id = new_id()
    assert start(client, chat_id).status_code == 202
    events(client, chat_id)
    assert (agent.asks[-1]["limits"] or {}) == {}

    async def disabled_down(collection, key):
        if collection == "account_agents":
            raise DbGatewayUnavailable("disabled agents unavailable")
        return await original(collection, key)

    monkeypatch.setattr(db_gateway, "get", disabled_down)
    response = start(client, new_id())
    assert (response.status_code, response.json()["detail"]) == (503, "Account agents storage is unavailable")
