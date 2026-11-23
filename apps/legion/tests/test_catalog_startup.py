import asyncio
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from src.runtime import config_files, treasury_bootstrap


def test_bootstrap_reads_config_and_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(config_files, "CONFIGS_DIR", tmp_path)
    (tmp_path / "config_app.json").write_text('{"treasury_url": "http://file:29602"}')
    monkeypatch.delenv("TREASURY_URL", raising=False)
    assert treasury_bootstrap.treasury_address() == "http://file:29602"
    monkeypatch.setenv("TREASURY_URL", "http://env:29602/")
    assert treasury_bootstrap.treasury_address() == "http://env:29602"


@pytest.mark.parametrize("entry", [True, False])
def test_entry_registers_origin_and_other_agents_only_refresh(tmp_path, monkeypatch, auth_stack, entry):
    from src import server
    from src.citadel_auth import ServiceCatalog
    from src.runtime import service_catalog
    seen = []
    def handler(request):
        seen.append((request.method, request.url.path, request.content))
        return httpx.Response(200, json={"services": {}})
    catalog = ServiceCatalog(auth_stack["legion"], "http://treasury:29602", cache_path=tmp_path / "cache.json", transport=httpx.MockTransport(handler), interval=0.01)
    monkeypatch.setattr(server, "catalog", catalog)
    monkeypatch.setattr(server, "SPEC", replace(server.SPEC, entry=entry))
    monkeypatch.setattr(server, "_AGENT_URL", "http://legion.test:29603/mcp")
    monkeypatch.delenv("CITADEL_ADVERTISE_URL", raising=False)

    async def go():
        async with server._register_with_treasury():
            for _ in range(100):
                if any(path == "/services" for _, path, _ in seen):
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("catalog did not refresh")
    # Instance registration is independent of address registration.
    async def register_instance(*args, **kwargs):
        return True
    monkeypatch.setattr(server, "register_instance", register_instance)
    asyncio.run(go())
    addresses = [body for method, path, body in seen if method == "PUT" and path == "/services/legion"]
    assert addresses == ([b'{"url":"http://legion.test:29603"}'] if entry else [])
