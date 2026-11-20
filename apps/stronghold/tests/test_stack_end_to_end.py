from src.mcp_tools.scope import Scope
from src.mcp_tools.stack_tools import StackTools
from tests.conftest import IDENTITY
from tests.test_chats import A as CHAT, put


def test_rest_and_mcp_share_an_account_chats_stack(client):
    assert put(client, CHAT).status_code == 200
    items = ["example a", "example b", "example c"]
    for item in items:
        assert client.post(f"/stack/{CHAT}/items", json={"text": item}).status_code == 201

    tools = StackTools(client.app.state.stacks)
    listed = client.portal.call(tools.list, Scope(IDENTITY["uid"], CHAT))
    assert [item["text"] for item in listed["items"]] == items
    other = client.portal.call(tools.list, Scope("u-2", CHAT))
    assert other["ok"] is False and not other.get("items")
