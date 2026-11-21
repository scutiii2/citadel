import httpx
from fastapi.testclient import TestClient

from src import api
from src.config import Settings
from tests.auth_helpers import identity, service_auth


def test_armory_calls_use_current_catalog_address_on_each_request(tmp_path, monkeypatch, auth_stack, db_gateway, platform, agent):
    seen = []
    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(200, json={})
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kw: httpx.MockTransport(handler))
    app = api.create_app(auth_stack["stronghold"], Settings(data_dir=tmp_path), store=db_gateway,
                         platform=platform, agent_gateway=agent)
    with TestClient(app, headers=identity()) as client:
        client.auth = service_auth()
        app.state.catalog._known["armory"] = "http://armory.test:29600"
        assert client.delete("/brains/accounts/u-1").status_code == 204
        app.state.catalog._known["armory"] = "http://moved.test:29600"
        assert client.delete("/brains/accounts/u-1").status_code == 204
    assert seen == ["armory.test", "moved.test"]
