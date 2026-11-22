import httpx

from src.services.legion_ask import LegionAsk
from tests.test_legion_ask import FakeResult, FakeSession, patch
from tests.test_outside_routes import ENTRY, FakeDirectory, auth, login_admin, make_client, on_app_db

ROUTE = "/api/outside/stronghold/ask"
TOOLS = [
    "stronghold__tool_brain_search", "stronghold__tool_brain_read", "stronghold__tool_brain_list",
    "stronghold__tool_brain_write", "stronghold__tool_brain_update",
]


def test_a_legion_only_client_cannot_call_stronghold(client):
    _, key = make_client(client, services=["legion"])
    assert client.post(ROUTE, json={"question": "Hi"}, headers=auth(key)).status_code == 403


def test_a_stronghold_call_allows_only_the_five_tools_and_uses_the_same_budget(client, monkeypatch):
    session = FakeSession(FakeResult({"response": "Remembered.", "total_tokens": 50}))
    seen = patch(monkeypatch, session)
    client.app.state.legion_ask = LegionAsk()
    client.app.state.agent_directory = FakeDirectory(ENTRY)
    client_id, key = make_client(client, services=["stronghold"], budget_tokens=10)

    response = client.post(ROUTE, json={"question": "Remember my cat is Tom"}, headers=auth(key))
    assert response.status_code == 200
    assert response.json()["answer"] == "Remembered."
    assert response.json()["usage"] == {"total_tokens": 50, "budget_remaining": 0}
    [(tool, sent)] = session.calls
    assert tool == "ask" and seen["url"] == ENTRY.url
    username, email, uid = seen["identity"]
    assert uid.startswith("oc_") and username == f"outside:{uid}" and email == ""
    assert sent["disabled_tools"] == ["*", *[f"!{tool}" for tool in TOOLS]]
    assert sent["approval_mode"] == "deny" and sent["allowed_tools"] == TOOLS
    assert sent["enabled_extensions"] == [] and not sent["plan"] and not sent["ask_user"]

    refused = client.post(ROUTE, json={"question": "What is my cat's name?"}, headers=auth(key))
    assert refused.status_code == 429 and len(session.calls) == 1

    async def read_events(clients):
        return await clients.events(client_id)

    events = on_app_db(client, read_events)
    assert [(event.service, event.action, event.reason) for event in events] == [
        ("stronghold", "refused", "budget_exhausted"), ("stronghold", "call", ""),
    ]


def test_delete_purges_every_domain_even_if_one_purge_fails(client, upstream):
    login_admin(client)
    created = client.post("/api/admin/outside-clients", json={
        "name": "bot", "services": ["stronghold"], "budget_tokens": 10,
    })
    assert created.status_code == 201
    record = created.json()["client"]
    uid = record["uid"]

    def purge(request):
        return httpx.Response(503 if request.url.path.startswith("/stack/") else 204)

    upstream.handler = purge
    path = f"/api/admin/outside-clients/{record['id']}"
    assert client.delete(path).status_code == 204
    assert {request.url.path for request in upstream.requests if request.method == "DELETE"} == {
        f"/{domain}/accounts/{uid}" for domain in ("brain", "stack", "brain/proposals", "brain/shares")
    }
    assert client.get(path).status_code == 404
