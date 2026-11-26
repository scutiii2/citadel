import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from types import SimpleNamespace

import pytest

from src.citadel_auth import resolved, settings_store
from src.tools.mcp_client import config, mcp_upstream, transports


@pytest.mark.parametrize("saved", [None, "http://saved.test/mcp"])
def test_main_uses_catalog_default_and_saved_url_wins(tmp_path, monkeypatch, saved):
    db = tmp_path / "settings.db"
    if saved:
        settings_store.put(db, "servers", "main", {"label": "Tools", "transport": "http", "url": saved})
    monkeypatch.setattr(mcp_upstream, "_CONFIG_PATH", db)
    monkeypatch.setattr(mcp_upstream.catalog, "mcp_url", lambda: "http://catalog.test:29600/mcp")
    loaded = {}
    class Client:
        def connect_all(self, path, overrides, **kwargs):
            loaded.update(config.load_servers_config(path, overrides))
    monkeypatch.setattr(mcp_upstream, "client", Client())
    monkeypatch.setenv("MCP_SERVER_URL", "http://ignored.test/mcp")
    mcp_upstream.connect()
    assert resolved(loaded["main"].url) == (saved or "http://catalog.test:29600/mcp")


def test_cli_override_wins_over_saved_server(tmp_path, monkeypatch):
    db = tmp_path / "settings.db"
    settings_store.put(db, "servers", "main", {"label": "Tools", "transport": "http", "url": "http://saved/mcp"})
    monkeypatch.setattr(mcp_upstream, "_CONFIG_PATH", db)
    loaded = {}
    class Client:
        def connect_all(self, path, overrides, **kwargs):
            loaded.update(config.load_servers_config(path, overrides))
    monkeypatch.setattr(mcp_upstream, "client", Client())
    mcp_upstream.connect("http://cli/mcp")
    assert resolved(loaded["main"].url) == "http://cli/mcp"


def test_open_session_resolves_callable_again_after_reconnect(monkeypatch):
    targets = []
    current = {"url": "http://first/mcp"}
    async def reachable(url, timeout):
        targets.append(url)
    @asynccontextmanager
    async def stream(url, **kwargs):
        yield (None, None)
    class Session:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def initialize(self): pass
    monkeypatch.setattr(transports, "_check_tcp_reachable", reachable)
    monkeypatch.setattr(transports, "streamable_http_client", stream)
    monkeypatch.setattr(transports, "ClientSession", Session)
    server = config.ServerConfig("main", "Armory", "", "http", url=lambda: current["url"])
    async def go():
        async with AsyncExitStack() as stack:
            await transports.open_session(stack, server, 1)
        current["url"] = "http://second/mcp"
        async with AsyncExitStack() as stack:
            await transports.open_session(stack, server, 1)
    asyncio.run(go())
    assert targets == ["http://first/mcp", "http://second/mcp"]


def test_catalog_default_retries_failed_startup_connection(tmp_path, monkeypatch):
    from src.tools.mcp_client import registry
    current = {"url": "http://down/mcp"}
    targets = []
    async def open_session(stack, server, *args, **kwargs):
        url = resolved(server.url)
        targets.append(url)
        if url == "http://down/mcp":
            raise OSError("down")
        return SimpleNamespace(list_tools=list_tools)
    async def list_tools():
        return SimpleNamespace(tools=[])
    monkeypatch.setattr(registry, "open_session", open_session)
    async def go():
        client = registry.McpClientRegistry()
        await client.connect_all(tmp_path / "settings.db", {"main": lambda: current["url"]})
        current["url"] = "http://ready/mcp"
        await client.list_tools()
        await client.aclose()
    asyncio.run(go())
    assert targets == ["http://down/mcp", "http://ready/mcp"]
