"""An agent proposes, the user approves through the routes, the agent finds and marks it: one store, two doors."""

from src.mcp_tools.scope import Account
from src.mcp_tools.skill_tools import SkillTools
from tests.auth_helpers import identity


def test_propose_approve_search_mark(client):
    tools = SkillTools(client.app.state.skill_files)
    me = Account("u-1")
    other = identity(uid="u-2", username="bo", email="bo@example.com")

    proposed = client.portal.call(tools.propose, me, "Restart an app", "an app is hung", "stop it, then start it", "tool_srv_stopApp")
    skill_id = proposed["id"]
    assert client.portal.call(tools.search, me, "app hung")["count"] == 0  # not usable before approval
    assert [(s["id"], s["status"]) for s in client.get("/skills").json()] == [(skill_id, "proposed")]

    assert client.put(f"/skills/{skill_id}/status", json={"status": "active"}).status_code == 200
    found = client.portal.call(tools.search, me, "app hung")
    assert found["count"] == 1 and found["message"].startswith("1 approved skill(s):\n") and "stop it, then start it" in found["message"]
    assert client.portal.call(tools.mark, me, skill_id, "success")["recorded"] is True
    assert client.get("/skills").json()[0]["successes"] == 1

    assert client.portal.call(tools.search, Account("u-2"), "app hung")["count"] == 0
    assert client.get("/skills", headers=other).json() == []

    for _ in range(3):
        client.portal.call(tools.mark, me, skill_id, "failure")
    assert client.get("/skills").json()[0]["failing"] is True
    assert client.portal.call(tools.search, me, "app hung")["count"] == 0

    assert client.delete("/skills/accounts/u-1").status_code == 204
    assert client.get("/skills").json() == []
