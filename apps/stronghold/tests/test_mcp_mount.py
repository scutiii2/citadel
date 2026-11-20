import json

from src.citadel_auth import ServiceAuth
from src.document_store import DbGatewayUnavailable
from tests.auth_helpers import identity
from tests.test_chats import A as CHAT, put


def test_the_mcp_route_needs_service_authentication(client):
    anonymous = type(client)(client.app)  # no service auth, no requester
    response = anonymous.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response.status_code in (401, 403)


def test_other_routes_still_win_over_the_mount(client):
    assert client.get("/health").status_code == 200
    assert client.put("/health").status_code == 405


def test_the_server_offers_the_stack_and_brain_tools(client):
    listed = __import__("asyncio").run(client.app.state.mcp.list_tools())
    assert {tool.name for tool in listed} == {
        "tool_stack_add", "tool_stack_list", "tool_stack_remove", "tool_stack_pin",
        "tool_brain_search", "tool_brain_read", "tool_brain_list", "tool_brain_write", "tool_brain_update",
    }
    assert all(tool.description for tool in listed)
    write = next(tool for tool in listed if tool.name == "tool_brain_write")
    assert "Never save" in write.description


MCP = "http://127.0.0.1:29650/mcp"
ACCEPT = "application/json, text/event-stream"
INIT = {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "1"}}


def rpc(client, auth, method, params, *, headers=None, request_id=1):
    message = {"jsonrpc": "2.0", "method": method, "params": params}
    if request_id is not None:
        message["id"] = request_id
    return client.post(MCP, auth=auth, json=message, headers={
        "Accept": ACCEPT, "X-Citadel-Requester": "", **(headers or {}),
    })


def result(answer):
    if answer.headers["content-type"].startswith("application/json"):
        return answer.json()["result"]
    line = next(line for line in answer.text.splitlines() if line.startswith("data: "))
    return json.loads(line.removeprefix("data: "))["result"]


def test_signed_legion_calls_carry_verified_mcp_metadata(client, auth_stack, db_gateway, monkeypatch):
    assert put(client, CHAT).status_code == 200
    legion = ServiceAuth(auth_stack["legion"], "stronghold")
    started = rpc(client, legion, "initialize", INIT)
    assert started.status_code == 200
    headers = {"Mcp-Session-Id": started.headers["Mcp-Session-Id"]}
    assert rpc(client, legion, "notifications/initialized", {}, headers=headers, request_id=None).status_code == 202
    listed = rpc(client, legion, "tools/list", {}, headers=headers)
    tools = {tool["name"]: tool for tool in result(listed)["tools"]}
    assert all(tool["description"] for tool in tools.values())
    assert "Never save" in tools["tool_stack_add"]["description"]
    token = identity()["X-Citadel-Requester"]
    added = rpc(client, legion, "tools/call", {
        "name": "tool_stack_add", "arguments": {"text": "sample note"},
        "_meta": {"requester_token": token, "chat_id": CHAT},
    }, headers=headers)
    assert result(added)["structuredContent"]["ok"] is True
    assert client.get(f"/stack/{CHAT}").json()["used"] == 1

    malformed = rpc(client, legion, "tools/call", {
        "name": "tool_stack_add", "arguments": {"text": {"value": "sample malformed note"}},
        "_meta": {"requester_token": token, "chat_id": CHAT},
    }, headers=headers)
    assert result(malformed)["isError"] is True
    assert "sample malformed note" not in malformed.text

    async def unavailable(*args):
        raise DbGatewayUnavailable("sample storage error")

    monkeypatch.setattr(db_gateway, "get", unavailable)
    refused = rpc(client, legion, "tools/call", {
        "name": "tool_stack_list", "arguments": {},
        "_meta": {"requester_token": token, "chat_id": CHAT},
    }, headers=headers)
    assert result(refused)["structuredContent"] == {
        "ok": False, "message": "Short-term memory storage is unavailable.",
    }
    assert client.get(f"/stack/{CHAT}").status_code == 503


def test_portcullis_cannot_initialize_the_mcp_transport(client):
    assert rpc(client, client.auth, "initialize", INIT).status_code == 403


def test_a_signed_legion_call_can_write_a_brain_note_without_a_chat(client, auth_stack):
    legion = ServiceAuth(auth_stack["legion"], "stronghold")
    started = rpc(client, legion, "initialize", INIT)
    assert started.status_code == 200
    headers = {"Mcp-Session-Id": started.headers["Mcp-Session-Id"]}
    assert rpc(client, legion, "notifications/initialized", {}, headers=headers, request_id=None).status_code == 202
    token = identity()["X-Citadel-Requester"]
    written = rpc(client, legion, "tools/call", {
        "name": "tool_brain_write",
        "arguments": {"title": "A preference", "body": "Prefers oatmeal.", "tags": ["food"]},
        "_meta": {"requester_token": token},
    }, headers=headers)
    note = result(written)["structuredContent"]
    assert note["ok"] is True
    response = client.get("/brain/search", params={"q": "oatmeal"})
    assert response.status_code == 200
    assert [hit["id"] for hit in response.json()["results"]] == [note["file"]["id"]]
