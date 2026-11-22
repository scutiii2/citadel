"""Liveness and readiness through the Stronghold API."""

from tests.auth_helpers import service_auth


def test_health_is_open_and_ready_reports_dependencies(client):
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/ready", auth=service_auth())
    assert response.status_code == 200
    report = response.json()
    assert report["service"] == "stronghold" and report["status"] == "up"
    assert {item["name"] for item in report["dependencies"]} == {"treasury", "legion", "armory", "portcullis"}


def test_readiness_requires_service_auth(client):
    assert client.get("/ready", auth=None).status_code == 401


def test_health_is_available_before_treasury_registers(tmp_path, auth_stack, db_gateway, platform, agent, monkeypatch):
    import asyncio

    from fastapi.testclient import TestClient

    from src import api
    from src.config import Settings

    def pending(*args):
        return asyncio.create_task(asyncio.Event().wait())

    monkeypatch.setattr(api.ServiceCatalog, "start", lambda *args: None)
    monkeypatch.setattr(api, "register_in_background", pending)
    monkeypatch.setattr(api, "DbGatewayClient", lambda *args: db_gateway)
    app = api.create_app(auth_stack["stronghold"], Settings(data_dir=tmp_path / "data"),
                         platform=platform, agent_gateway=agent)
    with TestClient(app) as running:
        assert running.get("/health").json() == {"status": "ok"}
        assert app.state.schema_version is None
