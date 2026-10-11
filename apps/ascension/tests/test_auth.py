import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from src.app import create_app
from src.auth import load_token, requester
from src.sessions import GameSessions
from tests.conftest import signed_in
from tests.test_sessions import Clock


@pytest.fixture
def app():
    app = create_app()
    @app.get("/protected")
    def protected(owner: str = Depends(requester)):
        return {"owner": owner}
    return app


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer unknown"}, {"Authorization": "Basic unknown"}, {"Authorization": "Bearer"}, {"X-Requester-Username": "42", "X-Internal-Token": "old-internal"}])
def test_missing_invalid_or_legacy_auth_is_401(app, headers):
    with TestClient(app) as client:
        response = client.get("/protected", headers=headers)
        assert response.status_code == 401 and response.json() == {"error": "Not signed in"}


def test_bearer_session_controls_owner_and_instances_are_isolated(app):
    headers = signed_in(app, "42")
    headers["X-Requester-Username"] = "forged"
    with TestClient(app) as client:
        assert client.get("/protected", headers=headers).json() == {"owner": "42"}
        assert client.get("/protected", headers=signed_in(app, "99")).json() == {"owner": "99"}
        assert client.get("/health").json() == {"status": "ok"}


def test_expired_token_is_401(app):
    clock = Clock()
    app.state.sessions = GameSessions(60, clock=clock)
    headers = signed_in(app, "42")
    clock.now = 60
    with TestClient(app) as client:
        assert client.get("/protected", headers=headers).json() == {"error": "Not signed in"}
        assert client.get("/protected", headers=headers).status_code == 401


def test_load_token_reads_the_file(tmp_path, monkeypatch):
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    env = tmp_path / ".env"
    env.write_text("INTERNAL_API_TOKEN=abc\n", encoding="utf-8")
    assert load_token(env) == "abc"


def test_environment_wins_over_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", "from-env")
    env = tmp_path / ".env"
    env.write_text("INTERNAL_API_TOKEN=abc\n", encoding="utf-8")
    assert load_token(env) == "from-env"



def test_concurrent_expired_requests_return_401_without_thread_races(app):
    import asyncio
    import threading
    import httpx

    class ExpiryClock:
        def __init__(self):
            self.now = 0.0
            self.barrier = threading.Barrier(2)
        def __call__(self):
            if self.now >= 60:
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    # Coordinate legacy sync dependencies after both read the
                    # session, exposing double deletion from worker threads.
                    self.barrier.wait(timeout=2)
            return self.now

    async def go():
        clock = ExpiryClock()
        app.state.sessions = GameSessions(60, clock=clock)
        headers = signed_in(app, "42")
        clock.now = 60
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://game") as client:
            responses = await asyncio.gather(client.get("/protected", headers=headers), client.get("/protected", headers=headers))
        assert [response.status_code for response in responses] == [401, 401]
        assert all(response.json() == {"error": "Not signed in"} for response in responses)
    asyncio.run(go())
