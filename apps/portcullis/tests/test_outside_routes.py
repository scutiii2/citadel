"""POST /api/outside/legion/ask: the one door an outside client's key opens."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.services.agent_directory import AgentEntry
from src.services.legion_ask import LegionAnswer, LegionUnavailable
from src.services.outside_clients import OutsideClients
from tests.conftest import ADMIN_PASSWORD, ADMIN_USERNAME
from tests.test_admin import login

BODY = {"question": "What is 2 + 2?"}
ENTRY = AgentEntry(id="ember", label="Ember", url="http://ember.internal/mcp", entry=True, orchestrator=True)


def auth(key):
    return {"Authorization": f"Bearer {key}"}


def login_admin(client):
    login(client, ADMIN_USERNAME, ADMIN_PASSWORD)


def on_app_db(client, work):
    """Run `work(OutsideClients)` on the app's own database, on the app's event loop; commit."""

    async def run():
        async with client.app.state.database.sessions() as session:
            result = await work(OutsideClients(session))
            await session.commit()
            return result

    return client.portal.call(run)


def make_client(client, **extra):
    async def create(clients):
        made, key = await clients.create(**{**dict(name="bot", services=["legion"]), **extra})
        return made.id, key

    return on_app_db(client, create)


def used(client, client_id):
    async def read(clients):
        return (await clients.spent(await clients.get(client_id)))[0]

    return on_app_db(client, read)


@dataclass
class FakeLegion:
    next: dict = field(default_factory=lambda: {"text": "ok", "tokens": 1})
    fail: bool = False
    calls: list = field(default_factory=list)

    async def ask(self, url, client, question, history):
        self.calls.append({"url": url, "uid": client.uid, "question": question, "history": history})
        if self.fail:
            raise LegionUnavailable("Legion is unavailable")
        return LegionAnswer(text=self.next["text"], tokens=self.next["tokens"], request_id="req-1")


class FakeDirectory:
    def __init__(self, entry):
        self._entry = entry

    async def entry(self):
        return self._entry


@pytest.fixture
def fake_legion(client):
    legion = FakeLegion()
    client.app.state.legion_ask = legion
    client.app.state.agent_directory = FakeDirectory(ENTRY)
    return legion


@pytest.fixture
def no_entry_agent(client):
    client.app.state.agent_directory = FakeDirectory(None)


def test_a_valid_call_returns_the_answer_and_counts_the_tokens(client, fake_legion):
    client_id, key = make_client(client, budget_tokens=1000)
    fake_legion.next = {"text": "Four.", "tokens": 25}
    response = client.post("/api/outside/legion/ask", json=BODY, headers=auth(key))
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Four." and body["usage"] == {"total_tokens": 25, "budget_remaining": 975} and body["request_id"]
    assert fake_legion.calls[0]["question"] == "What is 2 + 2?" and fake_legion.calls[0]["url"] == ENTRY.url
    assert used(client, client_id) == 25


def test_there_is_no_login_cookie_path_in(client):
    response = client.post("/api/outside/legion/ask", json=BODY)
    assert response.status_code == 401 and response.json()["detail"] == "Invalid or missing key."


def test_a_bad_body_is_422_and_spends_nothing(client, fake_legion):
    _id, key = make_client(client)
    for body in ({}, {"question": ""}, {"question": "x" * 8001}, {"question": "q", "history": [{"role": "system", "content": "x"}]},
                 {"question": "q", "history": [{"role": "user", "content": "x"}] * 21}, {"question": "q", "extra": 1}):
        assert client.post("/api/outside/legion/ask", json=body, headers=auth(key)).status_code == 422
    assert fake_legion.calls == []


def test_the_budget_runs_out_and_the_next_call_is_refused_with_retry_after(client, fake_legion):
    _id, key = make_client(client, budget_tokens=30)
    fake_legion.next = {"text": "a", "tokens": 30}
    assert client.post("/api/outside/legion/ask", json=BODY, headers=auth(key)).status_code == 200
    refused = client.post("/api/outside/legion/ask", json=BODY, headers=auth(key))
    assert refused.status_code == 429 and int(refused.headers["retry-after"]) > 0
    assert len(fake_legion.calls) == 1


def test_legion_down_is_503_and_no_tokens_are_counted(client, fake_legion):
    client_id, key = make_client(client, budget_tokens=1000)
    fake_legion.fail = True
    response = client.post("/api/outside/legion/ask", json=BODY, headers=auth(key))
    assert response.status_code == 503 and "answer" not in response.json()
    assert used(client, client_id) == 0


def test_no_entry_agent_is_503(client, fake_legion, no_entry_agent):
    _id, key = make_client(client)
    assert client.post("/api/outside/legion/ask", json=BODY, headers=auth(key)).status_code == 503
    assert fake_legion.calls == []


def test_if_the_tokens_cannot_be_recorded_the_answer_is_withheld(client, fake_legion, monkeypatch):
    _id, key = make_client(client)

    async def broken(self, *args, **kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(OutsideClients, "record", broken)
    response = client.post("/api/outside/legion/ask", json=BODY, headers=auth(key))
    assert response.status_code == 503 and "answer" not in response.json()


def test_a_session_cookie_or_account_login_does_not_open_the_door(client):
    login_admin(client)
    assert client.post("/api/outside/legion/ask", json=BODY).status_code == 401


def test_the_outside_route_is_the_only_one_a_client_key_opens(client):
    _id, key = make_client(client)
    for path in ("/api/chats", "/api/admin/outside-clients", "/api/usage", "/api/agent"):
        assert client.get(path, headers=auth(key)).status_code in (401, 403, 404)


def test_a_422_never_echoes_the_question(client, fake_legion):
    _id, key = make_client(client)
    secret = "TOPSECRETQUESTION" * 600
    response = client.post("/api/outside/legion/ask", json={"question": secret}, headers=auth(key))
    assert response.status_code == 422 and "TOPSECRET" not in response.text
    assert set(response.json()["detail"][0]) == {"loc", "msg", "type"}
