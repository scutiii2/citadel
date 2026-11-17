import asyncio
import json
from dataclasses import replace

import httpx
from fastapi.testclient import TestClient

from src import config
from src.citadel_auth import ServiceCatalog
from tests.conftest import make_settings, FakeEmailSender, FakeServerTools, FakeUpstream


def test_treasury_url_from_file_and_environment(tmp_path, monkeypatch):
    (tmp_path / "config_app.json").write_text('{"treasury_url":"http://file:29602"}')
    monkeypatch.setattr(config, "CONFIGS_DIR", tmp_path)
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(config, "ensure_env_file", lambda *args: None)
    monkeypatch.delenv("TREASURY_URL", raising=False)
    assert config.load_settings().treasury_url == "http://file:29602"
    monkeypatch.setenv("TREASURY_URL", "http://env:29602")
    assert config.load_settings().treasury_url == "http://env:29602"


def test_lifespan_registers_portcullis(tmp_path, monkeypatch):
    from src import app as wiring
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        return httpx.Response(200, json={"services": {}})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(wiring.httpx, "AsyncClient", lambda **kw: real_client(**{"transport": transport, **kw}))
    monkeypatch.setattr(wiring, "ServiceCatalog", lambda *a, **kw: ServiceCatalog(*a, transport=transport, **kw))
    settings = replace(make_settings(tmp_path), advertise_url="http://portcullis.test:29601")
    app = wiring.create_app(settings, email_sender=FakeEmailSender(), server_tools=FakeServerTools(), upstream_transport=transport)
    with TestClient(app) as client:
        async def wait_registered():
            for _ in range(100):
                if any(p == "/services/portcullis" for _, p, _ in seen):
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("catalog did not register")
        client.portal.call(wait_registered)
        assert ("PUT", "/services/portcullis", {"url": "http://portcullis.test:29601"}) in seen
