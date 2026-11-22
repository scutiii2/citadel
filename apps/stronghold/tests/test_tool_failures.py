# apps/stronghold/tests/test_tool_failures.py
import asyncio

import httpx

import pytest

from src.citadel_auth import ServiceAuth
from src.document_store import DbGatewayClient
from src.mcp_tools.failures import guarded
from tests.auth_helpers import identity
from tests.test_mcp_mount import CHAT, INIT, put, result, rpc


def test_a_treasury_outage_becomes_a_numbered_failure():
    request = httpx.Request("GET", "http://treasury/x")

    @guarded("treasury")
    async def tool():
        raise httpx.ConnectError("secret-host refused", request=request)

    text = asyncio.run(tool())
    assert text == "[1002] DEP_UNAVAILABLE treasury unavailable"
    assert "secret" not in text


def test_success_passes_through():
    @guarded("treasury")
    async def tool():
        return "ok"

    assert asyncio.run(tool()) == "ok"


@pytest.mark.parametrize(("name", "arguments", "target", "member"), [
    ("tool_stack_list", {}, "stacks", "view"),
    ("tool_brain_propose", {"title": "Tea", "body": "Prefers tea.", "item_ids": [1]}, "brain_proposals", "propose"),
    ("tool_ticket_listMyTickets", {}, "tickets", "list_tickets"),
    ("tool_usage_summary", {}, "usage", "report"),
])
def test_signed_tool_returns_numbered_storage_failure(client, auth_stack, monkeypatch, name, arguments, target, member):
    assert put(client, CHAT).status_code == 200
    legion = ServiceAuth(auth_stack["legion"], "stronghold")
    initialized = rpc(client, legion, "initialize", INIT)
    headers = {"Mcp-Session-Id": initialized.headers["Mcp-Session-Id"]}
    assert rpc(client, legion, "notifications/initialized", {}, headers=headers, request_id=None).status_code == 202

    async def down(*args, **kwargs):
        raise httpx.ConnectError("hidden host")

    monkeypatch.setattr(getattr(client.app.state, target), member, down)
    answer = result(rpc(client, legion, "tools/call", {
        "name": name, "arguments": arguments,
        "_meta": {"requester_token": identity()["X-Citadel-Requester"], "chat_id": CHAT},
    }, headers=headers))
    assert answer["isError"] is True
    assert answer["content"][0]["text"] == "[1002] DEP_UNAVAILABLE treasury unavailable"


def test_treasury_auth_status_survives_the_document_store():
    @guarded("treasury")
    async def tool():
        transport = httpx.MockTransport(lambda request: httpx.Response(403, text="restricted details"))
        async with httpx.AsyncClient(transport=transport, base_url="http://treasury") as client:
            store = DbGatewayClient(client, "stronghold", "data")
            return await store.get("tickets", "1")

    assert asyncio.run(tool()) == "[1004] DEP_AUTH_REJECTED treasury rejected the service token"


def test_a_remote_disconnect_is_retryable():
    def disconnected(request):
        raise httpx.RemoteProtocolError("private details", request=request)

    @guarded("treasury")
    async def tool():
        async with httpx.AsyncClient(transport=httpx.MockTransport(disconnected), base_url="http://treasury") as client:
            store = DbGatewayClient(client, "stronghold", "data")
            return await store.get("tickets", "1")

    assert asyncio.run(tool()) == "[1002] DEP_UNAVAILABLE treasury unavailable"
