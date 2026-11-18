import httpx

from src.config import load_settings


def test_treasury_url_comes_from_the_environment_over_the_file(monkeypatch):
    monkeypatch.setenv("TREASURY_URL", "http://treasury:29602")
    assert load_settings().treasury_url == "http://treasury:29602"


def test_treasury_url_defaults_to_the_local_address(monkeypatch):
    monkeypatch.delenv("TREASURY_URL", raising=False)
    assert load_settings().treasury_url == "http://127.0.0.1:29602"


def test_treasury_url_comes_from_config_and_env_wins(tmp_path, monkeypatch):
    path = tmp_path / "config_app.json"
    path.write_text('{"treasury_url": "http://from-file:29602", "advertise_url": "http://stronghold:29650"}')
    monkeypatch.setenv("STRONGHOLD_CONFIG", str(path))
    monkeypatch.setenv("STRONGHOLD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("TREASURY_URL", raising=False)
    assert load_settings().treasury_url == "http://from-file:29602"
    assert load_settings().advertise_url == "http://stronghold:29650"
    monkeypatch.setenv("TREASURY_URL", "http://from-env:29602")
    assert load_settings().treasury_url == "http://from-env:29602"


def test_lifespan_registers_its_advertised_address(tmp_path, monkeypatch, auth_stack, platform, agent, legion):
    import asyncio
    import json
    from fastapi.testclient import TestClient
    from src import api
    from src.citadel_auth import ServiceCatalog
    from src.config import Settings
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        if request.url.path == "/services":
            return httpx.Response(200, json={"services": {}})
        if request.method == "PUT":
            return httpx.Response(200, json={"saved": "stronghold"})
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(api.httpx, "AsyncClient", lambda **kwargs: real_client(**{"transport": transport, **kwargs}))
    monkeypatch.setattr(api, "ServiceCatalog", lambda *args, **kwargs: ServiceCatalog(*args, transport=transport, **kwargs))
    settings = Settings(data_dir=tmp_path / "data", advertise_url="http://stronghold.test:29650")
    app = api.create_app(auth_stack["stronghold"], settings, platform=platform, agent_gateway=agent,
                         legion=real_client(transport=transport))
    with TestClient(app) as client:
        async def wait_registered():
            for _ in range(100):
                if any(path == "/services/stronghold" for _, path, _ in seen):
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("catalog did not register")
        client.portal.call(wait_registered)
        assert ("PUT", "/services/stronghold", {"url": "http://stronghold.test:29650"}) in seen
