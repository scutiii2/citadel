from dataclasses import replace

from tests.auth_helpers import IdentityHeaders
from tests.conftest import IDENTITY

BO = IdentityHeaders(uid="u-2", username="bob", email="bob@example.com")
CHAT = "chat-1"


def seed(client, uid=None, title="Tea habits", body="The user likes green tea.", **extra):
    """Create a pending proposal the way the MCP tool does, in-process (assumption d: copy the way test_stack_routes seeds)."""
    proposals = client.app.state.brain_proposals
    made, _ = client.portal.call(lambda: proposals.propose(uid or IDENTITY["uid"], CHAT, title, body, [], **extra))
    return made


def test_list_detail_accept_and_logs(client, platform):
    made = seed(client, folder="drinks")
    listed = client.get("/brain/proposals").json()["proposals"]
    assert [p["id"] for p in listed] == [made["id"]] and "body" not in listed[0]
    assert client.get("/brain/proposals", headers=BO).json()["proposals"] == []
    seen = client.get(f"/brain/proposals/{made['id']}").json()
    assert seen["body"] == "The user likes green tea." and "agent wrote" in seen["notice"].lower()
    assert client.get(f"/brain/proposals/{made['id']}", headers=BO).status_code == 404
    done = client.post(f"/brain/proposals/{made['id']}/accept", json={"title": "Green tea", "folder": "likes"})
    assert done.status_code == 200 and done.json()["status"] == "accepted" and done.json()["removed"] == 0
    mine = client.get("/brain/files").json()["files"]
    assert [(f["title"], f["folder"], f["source"]) for f in mine] == [("Green tea", "likes", "automatic")]
    assert client.get("/brain/proposals").json()["proposals"] == []
    assert [a for _, a, _ in platform.actions if a.startswith("brain.proposal")] == ["brain.proposal_accept"]
    assert all("tea" not in m.lower() for _, _, m in platform.actions)


def test_decline_and_a_decided_proposal(client, platform):
    made = seed(client)
    assert client.post(f"/brain/proposals/{made['id']}/decline", headers=BO).status_code == 404
    assert client.post(f"/brain/proposals/{made['id']}/decline").json()["status"] == "declined"
    again = client.post(f"/brain/proposals/{made['id']}/accept")
    assert again.status_code == 409 and "already decided" in again.json()["detail"]
    assert "brain.proposal_decline" in [a for _, a, _ in platform.actions]


def test_a_full_long_term_memory_refuses_the_accept_and_keeps_it_pending(client):
    made = seed(client)
    state = client.app.state.brain_files
    original = state.limits
    state.limits = replace(original, max_files=0)
    try:
        refused = client.post(f"/brain/proposals/{made['id']}/accept")
    finally:
        state.limits = original
    assert refused.status_code == 409
    assert len(client.get("/brain/proposals").json()["proposals"]) == 1


def test_validation_and_purge(client):
    assert client.get("/brain/proposals/not-hex").status_code == 422
    made = seed(client)
    assert client.post(f"/brain/proposals/{made['id']}/accept", json={"folder": "../etc"}).status_code == 422
    assert client.delete(f"/brain/proposals/accounts/{IDENTITY['uid']}").status_code == 204
    assert client.get("/brain/proposals").json()["proposals"] == []
