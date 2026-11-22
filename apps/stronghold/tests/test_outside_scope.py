import pytest

from src.citadel_auth import ServiceAuth
from src.mcp_tools import scope
from tests.auth_helpers import identity
from tests.test_brain_global import as_writer
from tests.test_mcp_mount import INIT, result, rpc
from tests.test_mcp_scope import FakeApp, fake_context

OUTSIDE = "oc_0123456789ab"


async def test_outside_accounts_must_be_explicitly_allowed(monkeypatch):
    assert scope.is_outside(OUTSIDE)
    assert not scope.is_outside("u-1")
    assert not scope.is_outside("")
    fake_context(monkeypatch, uid=OUTSIDE)
    with pytest.raises(scope.ScopeError, match="outside clients"):
        async with scope.resolve_account(FakeApp):
            pytest.fail("Outside requester admitted without opt-in")
    async with scope.resolve_account(FakeApp, outside_ok=True) as account:
        assert account.uid == OUTSIDE
    with pytest.raises(scope.ScopeError, match="outside clients"):
        async with scope.resolve_scope(FakeApp):
            pytest.fail("Outside requester admitted with a chat id")


@pytest.fixture
def outside_tool(client, auth_stack):
    legion = ServiceAuth(auth_stack["legion"], "stronghold")
    started = rpc(client, legion, "initialize", INIT)
    assert started.status_code == 200
    headers = {"Mcp-Session-Id": started.headers["Mcp-Session-Id"]}
    assert rpc(client, legion, "notifications/initialized", {}, headers=headers, request_id=None).status_code == 202

    def call(name, arguments, *, uid=OUTSIDE):
        token = identity(uid=uid, username=f"outside:{uid}", email="")["X-Citadel-Requester"]
        response = rpc(client, legion, "tools/call", {
            "name": name, "arguments": arguments, "_meta": {"requester_token": token},
        }, headers=headers)
        return result(response)["structuredContent"]

    return call


def test_the_five_brain_tools_only_access_the_signed_outside_folder(client, platform, outside_tool):
    as_writer(platform)
    global_note = client.post("/brain/global/files", json={"title": "Tea rule", "body": "Global tea."}).json()
    other_note = outside_tool("tool_brain_write", {"title": "Tea preference", "body": "Other tea."}, uid="oc_abcdef012345")
    own_note = outside_tool("tool_brain_write", {"title": "Tea preference", "body": "Own tea."})
    assert own_note["ok"] and other_note["ok"]
    own_id = own_note["file"]["id"]

    listed = outside_tool("tool_brain_list", {})
    assert listed["ok"] and [note["id"] for note in listed["files"]] == [own_id]
    assert not outside_tool("tool_brain_list", {"scope": "global"})["ok"]
    found = outside_tool("tool_brain_search", {"query": "tea"})
    assert [(note["id"], note["scope"]) for note in found["results"]] == [(own_id, "own")]

    assert outside_tool("tool_brain_read", {"file_id": own_id})["file"]["body"] == "Own tea."
    updated = outside_tool("tool_brain_update", {"file_id": own_id, "body": "Own black tea."})
    assert updated["ok"] and updated["file"]["body"] == "Own black tea."
    for file_id in (global_note["id"], other_note["file"]["id"]):
        assert not outside_tool("tool_brain_read", {"file_id": file_id})["ok"]
        assert not outside_tool("tool_brain_update", {"file_id": file_id, "body": "overwrite"})["ok"]


@pytest.mark.parametrize(("name", "args"), [
    ("tool_ticket_listMyTickets", {}),
    ("tool_usage_summary", {}),
    ("tool_skill_search", {}),
    ("tool_skill_propose", {"title": "Tea", "when_to_use": "Tea time", "steps": "Steep tea"}),
    ("tool_stack_list", {}),
    ("tool_brain_propose", {"title": "Tea", "body": "Drink tea"}),
])
def test_outside_requesters_cannot_use_other_tools(outside_tool, name, args):
    assert outside_tool(name, args) == {"ok": False, "message": "Not available to outside clients."}
