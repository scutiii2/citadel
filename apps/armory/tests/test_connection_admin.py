import httpx
from starlette.applications import Starlette
from starlette.testclient import TestClient

from src.services.service_auth import install_auth
from tests.auth_helpers import FreshHeaders


def test_admin_records_keep_credentials_write_only_and_test_rest(tmp_path):
    from src.connection_admin import install_connection_admin
    from src.services.connections import ConnectionStore

    def health(request):
        assert request.url.path == "/health"
        assert request.headers["X-Internal-Token"] == "tool-test-value"
        return httpx.Response(200, json={"ok": True, "ready": True})

    app = Starlette()
    install_auth(app)
    install_connection_admin(app, ConnectionStore(tmp_path / "settings.db"),
                             httpx.AsyncClient(transport=httpx.MockTransport(health)))
    path = "/admin/connections"
    with TestClient(app) as client:
        assert client.get(path, headers=FreshHeaders(caller="stronghold")).status_code == 403
        before = client.get(path, headers=FreshHeaders())
        assert [item["name"] for item in before.json()] == ["bard", "scribe", "reader"]
        updated = client.patch(f"{path}/bard", headers=FreshHeaders(), json={
            "rest": {"base_url": "http://bard", "auth": {"kind": "token", "token": "tool-test-value"}}
        })
        assert updated.status_code == 200
        assert updated.json()["rest"]["auth"] == {"kind": "token", "configured": True}
        assert "tool-test-value" not in updated.text
        listed = client.get(path, headers=FreshHeaders())
        assert "tool-test-value" not in listed.text
        checked = client.post(f"{path}/bard/test/rest", headers=FreshHeaders())
        assert checked.json()["ok"] is True
        assert "tool-test-value" not in checked.text
        assert client.delete(f"{path}/bard", headers=FreshHeaders()).status_code == 400
