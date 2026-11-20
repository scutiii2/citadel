"""A user and an agent share one account's long-term memory through the same BrainFiles."""

from src.mcp_tools.brain_tools import BrainTools
from src.mcp_tools.scope import Account
from tests.auth_helpers import identity

def test_user_and_agent_through_one_store(client):
    tools = BrainTools(client.app.state.brain_files)
    me = Account("u-1")
    other = identity(uid="u-2", username="bo", email="bo@example.com")

    made = client.post("/brain/files", json={"title": "Diet", "body": "The user avoids gluten.", "tags": ["food"]}).json()
    found = client.portal.call(tools.search, me, "gluten", None)
    assert [r["id"] for r in found["results"]] == [made["id"]] and found["results"][0]["source_label"] == "written by the user"

    refused = client.portal.call(tools.update, me, made["id"], None, "The user loves gluten.", None, None)
    assert refused["ok"] is False
    assert client.get(f"/brain/files/{made['id']}").json()["body"] == "The user avoids gluten."
    client.put(f"/brain/files/{made['id']}", json={"agent_editable": True})
    assert client.portal.call(tools.update, me, made["id"], None, "The user avoids gluten and nuts.", None, None)["ok"] is True

    wrote = client.portal.call(tools.write, me, "Agent finding", "Prefers tea.", ["tea"], "learned")["file"]
    shown = client.get(f"/brain/files/{wrote['id']}").json()
    assert shown["source"] == "automatic" and shown["warning"]
    client.put(f"/brain/files/{wrote['id']}", json={"body": "Prefers coffee."})
    assert client.get(f"/brain/files/{wrote['id']}").json()["edited"] is True
    assert client.portal.call(tools.read, me, wrote["id"])["file"]["body"] == "Prefers coffee."
    assert client.post(f"/brain/files/{wrote['id']}/revert").json()["body"] == "Prefers tea."

    assert client.portal.call(tools.search, Account("u-2"), "gluten", None)["count"] == 0
    assert client.get("/brain/files", headers=other).json()["files"] == []
    assert client.get("/brain/summary").json()["files"] == 2
    assert client.delete("/brain/accounts/u-1").status_code == 204
    assert client.get("/brain/files").json() == {"files": [], "folders": []}
