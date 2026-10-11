import pytest
from fastapi.testclient import TestClient
from src.app import create_app
from src.ember_identity import IdentityUnavailable
from src.sessions import GameSessions
from src.session_routes import RedeemLimiter


class FakeIdentity:
    def __init__(self, owner="42", fail=False):
        self.owner = owner
        self.fail = fail
        self.calls = []
    async def redeem(self, ticket):
        self.calls.append(ticket)
        if self.fail:
            raise IdentityUnavailable()
        return self.owner


class Clock:
    def __init__(self):
        self.now = 0.0
    def __call__(self):
        return self.now


def test_redeem_opens_a_session_without_internal_header():
    sessions, identity = GameSessions(120), FakeIdentity()
    with TestClient(create_app(internal_token="configured", sessions=sessions, identity=identity)) as client:
        response = client.post("/session/redeem", json={"ticket": "one-time"})
        assert response.status_code == 200 and response.json()["expires_in"] == 120
        assert sessions.owner_of(response.json()["token"]) == "42"
        assert identity.calls == ["one-time"]
        assert "set-cookie" not in response.headers


@pytest.mark.parametrize("owner,fail,status,message", [(None, False, 401, "Invalid ticket"), ("42", True, 502, "Ember is not available")])
def test_redeem_errors(owner, fail, status, message):
    with TestClient(create_app(identity=FakeIdentity(owner, fail))) as client:
        response = client.post("/session/redeem", json={"ticket": "bad"})
        assert response.status_code == status and response.json() == {"error": message}


@pytest.mark.parametrize("body", [{}, [], {"ticket": 1}, {"ticket": ""}, {"ticket": "x", "owner": "forged"}])
def test_malformed_body_is_400_without_identity_call(body):
    identity = FakeIdentity()
    with TestClient(create_app(identity=identity)) as client:
        response = client.post("/session/redeem", json=body)
        assert response.status_code == 400
        assert identity.calls == []


def test_rate_limit_counts_bad_tickets_is_per_ip_and_resets():
    clock, identity = Clock(), FakeIdentity(owner=None)
    app = create_app(identity=identity)
    app.state.redeem_limiter = RedeemLimiter(clock=clock)
    with TestClient(app, client=("192.0.2.1", 1234)) as first, TestClient(app, client=("192.0.2.2", 1234)) as second:
        for _ in range(10):
            assert first.post("/session/redeem", json={"ticket": "bad"}).status_code == 401
        assert first.post("/session/redeem", json={"ticket": "bad"}).status_code == 429
        assert len(identity.calls) == 10
        assert second.post("/session/redeem", json={"ticket": "bad"}).status_code == 401
        clock.now = 60
        assert first.post("/session/redeem", json={"ticket": "bad"}).status_code == 401


def test_malformed_json_and_bodies_cannot_bypass_rate_limit():
    with TestClient(create_app(identity=FakeIdentity())) as client:
        for _ in range(10):
            assert client.post("/session/redeem", content="{", headers={"Content-Type": "application/json"}).status_code == 400
        assert client.post("/session/redeem", json={"ticket": "x"}).status_code == 429



def test_dev_owner_is_disabled_by_default_and_only_dev_ticket_bypasses_ember(config):
    from dataclasses import replace
    identity = FakeIdentity(owner=None)
    with TestClient(create_app(config=config, identity=identity)) as client:
        assert client.post("/session/redeem", json={"ticket": "dev"}).status_code == 401
    dev_config = replace(config, dev_fake_owner="local-player")
    app = create_app(config=dev_config, identity=identity)
    with TestClient(app) as client:
        response = client.post("/session/redeem", json={"ticket": "dev"})
        assert response.status_code == 200
        assert app.state.sessions.owner_of(response.json()["token"]) == "local-player"
        assert response.json()["expires_in"] == 8 * 3600
        assert identity.calls == ["dev"]
        assert client.post("/session/redeem", json={"ticket": "other"}).status_code == 401
        assert identity.calls == ["dev", "other"]


def test_runtime_owns_and_closes_identity_client(config, monkeypatch):
    import httpx
    from src import app as app_module
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"account_id": "42", "display_name": "Player"})))
    monkeypatch.setattr(app_module.httpx, "AsyncClient", lambda **kwargs: client)
    app = create_app(config=config, internal_token="test-internal")
    assert app.state.identity is None
    with TestClient(app) as browser:
        assert app.state.identity is not None
        assert browser.post("/session/redeem", json={"ticket": "one-time"}).status_code == 200
    assert client.is_closed and app.state.identity is None
