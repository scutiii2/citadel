"""Readiness reports for signed peers and staff."""

import httpx

from src.citadel_auth import ServiceAuth, sign_assertion
from tests.test_admin import login, make_member
from tests.test_outside_routes import login_admin


def test_open_health_and_signed_ready(client, auth_stack):
    assert client.get("/api/health").json() == client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 401
    assertion = sign_assertion(auth_stack["stronghold"], "portcullis")
    response = client.get("/ready", headers={"Authorization": f"Bearer {assertion}"})
    assert response.status_code == 200
    assert {row["name"] for row in response.json()["dependencies"]} == {"treasury", "stronghold", "legion", "armory"}


def test_admin_ready_requires_settings_manage(client, email):
    make_member(client, email)
    login(client, "alice")
    assert client.get("/api/admin/ready").status_code == 403


def test_admin_ready_reports_available_peers_and_outages(client, monkeypatch):
    async def upstream(url, **kwargs):
        assert isinstance(kwargs["auth"], ServiceAuth)
        name = kwargs["auth"].audience
        if name == "treasury":
            raise httpx.ConnectError("private host")
        return httpx.Response(200, request=httpx.Request("GET", url),
                              json={"service": name, "status": "up", "dependencies": []})

    monkeypatch.setattr(client.app.state.upstream, "get", upstream)
    login_admin(client)
    response = client.get("/api/admin/ready")
    assert response.status_code == 200
    reports = response.json()
    assert set(reports) == {"portcullis", "stronghold", "legion", "armory", "treasury"}
    assert reports["treasury"] == {"service": "treasury", "status": "down"}
    assert reports["legion"]["status"] == "up"
