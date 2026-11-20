"""One account shares, another accepts, an agent reads; the global brain takes a share through review."""

from src.mcp_tools.brain_tools import BrainTools
from src.mcp_tools.scope import Account
from tests.auth_helpers import IdentityHeaders

BO = IdentityHeaders(uid="u-2", username="bob", email="bob@example.com")


def test_share_accept_search_review_and_purge(client, platform):
    me = client.get("/whoami").json()["username"]
    tools = BrainTools(client.app.state.brain_files, client.app.state.global_brain)
    file = client.post("/brain/files", json={"title": "Tea", "body": "I drink green tea. See [my diet](private/diet.md)."}).json()

    given = client.post("/brain/shares", json={"kind": "file", "file_id": file["id"], "recipient": "bob"}).json()
    assert client.portal.call(tools.search, Account("u-2"), "tea", None)["count"] == 0  # nothing lands before consent
    accepted = client.post(f"/brain/shares/{given['id']}/accept", headers=BO).json()
    found = client.portal.call(tools.search, Account("u-2"), "tea", None)
    assert found["count"] == 1 and found["results"][0]["source_label"] == "shared by another account"
    read = client.portal.call(tools.read, Account("u-2"), accepted["result_id"])
    assert read["file"]["body"] == "I drink green tea. See my diet." and read["file"]["shared_from"] == me
    refused = client.portal.call(tools.update, Account("u-2"), accepted["result_id"], None, "agent edit", None, None)
    assert refused["ok"] is False

    platform.granted["u-2"] = {"chat.use", "brain.global.write"}
    queued = client.post("/brain/shares", json={"kind": "file", "file_id": file["id"], "to_global": True}).json()
    client.post(f"/brain/global/shares/{queued['id']}/approve", headers=BO)
    seen = client.portal.call(tools.search, Account("u-3"), "tea", None)
    assert [(r["scope"], r["source_label"]) for r in seen["results"]] == [("global", "global brain")]

    assert client.delete("/brain/shares/accounts/u-1").status_code == 204
    assert client.get("/brain/shares/sent").json()["shares"] == []
    assert client.get("/brain/files", headers=BO).json()["files"][0]["shared_from"] == me  # an accepted copy stays
