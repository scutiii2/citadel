import asyncio
from types import SimpleNamespace

import pytest

from src.tools.mcp_client.config import load_servers_config
from src.citadel_auth import settings_store

STRONGHOLD = {"stronghold": {"label": "Stronghold", "transport": "http", "url": "http://stronghold.test/mcp"}}


def test_a_builtin_is_added_when_nothing_is_saved(tmp_path):
    servers = load_servers_config(tmp_path / "settings.db", None, STRONGHOLD)
    assert servers["stronghold"].url == "http://stronghold.test/mcp"
    assert servers["stronghold"].label == "Stronghold"


def test_a_saved_entry_with_the_same_id_wins(tmp_path):
    path = tmp_path / "settings.db"
    settings_store.put(path, "servers", "stronghold", {"label": "Mine", "transport": "http", "url": "http://mine.test/mcp"})
    servers = load_servers_config(path, None, STRONGHOLD)
    assert servers["stronghold"].url == "http://mine.test/mcp"


def test_no_builtins_changes_nothing(tmp_path):
    assert load_servers_config(tmp_path / "settings.db") == {}


def test_catalog_url_stays_lazy_and_is_resolved_again(tmp_path):
    url = "http://down.test/mcp"
    builtin = {**STRONGHOLD["stronghold"], "url": lambda: url}
    server = load_servers_config(tmp_path / "settings.db", builtins={"stronghold": builtin})["stronghold"]
    url = "http://ready.test/mcp"
    assert server.url() == "http://ready.test/mcp"


def test_a_down_builtin_does_not_delay_main_and_retries_in_the_background(tmp_path, monkeypatch):
    from src.tools.mcp_client import registry

    db = tmp_path / "settings.db"
    settings_store.put(db, "servers", "main", {"label": "Armory", "transport": "http", "url": "http://armory.test/mcp"})

    async def run():
        attempt = asyncio.Event()
        allow_failure = asyncio.Event()
        retry = asyncio.Event()

        async def list_tools():
            return SimpleNamespace(tools=[])

        async def open_session(stack, config, *args, **kwargs):
            if config.id == "stronghold":
                if not attempt.is_set():
                    attempt.set()
                    await allow_failure.wait()
                    raise ConnectionRefusedError("test port is closed")
                await retry.wait()
            return SimpleNamespace(list_tools=list_tools)

        async def status(server_id, expected):
            async with asyncio.timeout(2):
                while True:
                    if any(s.id == server_id and s.status == expected for s in client.statuses()):
                        return
                    await asyncio.sleep(0.01)

        monkeypatch.setattr(registry, "open_session", open_session)
        monkeypatch.setattr(registry, "ORIGIN_COOLDOWN_SECONDS", 0.02)
        client = registry.McpClientRegistry()
        try:
            await asyncio.wait_for(client.connect_all(db, builtins=STRONGHOLD), timeout=1)
            await asyncio.wait_for(attempt.wait(), timeout=1)
            await status("main", "connected")
            assert await asyncio.wait_for(client.list_tools(), timeout=1) == []
            allow_failure.set()
            await status("stronghold", "error")
            retry.set()
            await status("stronghold", "connected")
            await status("main", "connected")
        finally:
            await client.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("saved, trusted", [
    ({"transport": "stdio", "command": "external"}, False),
    ({"transport": "http", "url": "http://outside.test/mcp"}, False),
    ({"transport": "http", "url": "http://stronghold.test/mcp"}, True),
])
def test_only_the_trusted_http_destination_gets_internal_credentials(tmp_path, monkeypatch, saved, trusted):
    from src.tools.mcp_client import registry

    db = tmp_path / "settings.db"
    settings_store.put(db, "servers", "stronghold", {"label": "Saved", **saved})
    auth = object()
    meta = {"requester_token": "sample", "chat_id": "chat-1"}
    applied_auth = []

    class Session:
        async def list_tools(self):
            return SimpleNamespace(tools=[])

        async def call_tool(self, name, arguments, **extra):
            return extra.get("meta")

    async def open_session(stack, config, *args, **options):
        applied_auth.append(options.get("auth"))
        return Session()

    monkeypatch.setattr(registry, "open_session", open_session)

    async def run():
        client = registry.McpClientRegistry()
        try:
            await client.connect_all(db, builtins=STRONGHOLD, auth_by_server={"stronghold": auth})
            async with asyncio.timeout(2):
                while not any(status.status == "connected" for status in client.statuses()):
                    await asyncio.sleep(0.01)
            sent = await client.call_tool("stronghold__tool_stack_list", {}, meta=meta)
            assert sent == (meta if trusted else None)
            assert applied_auth == [auth if trusted else None]
        finally:
            await client.aclose()

    asyncio.run(run())


def test_stronghold_stream_rejects_cross_origin_redirects(monkeypatch):
    from contextlib import AsyncExitStack, asynccontextmanager
    from functools import partial

    from src.tools.mcp_client import transports
    from src.tools.mcp_client.config import validate_server

    transport_options = {}

    async def reachable(url, timeout):
        pass

    @asynccontextmanager
    async def stream(url, **options):
        transport_options.update(options)
        yield None, None, None

    class Session:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def initialize(self):
            pass

    monkeypatch.setattr(transports, "_check_tcp_reachable", reachable)
    monkeypatch.setattr(transports, "streamablehttp_client", stream)
    monkeypatch.setattr(transports, "ClientSession", Session)
    config = validate_server("stronghold", STRONGHOLD["stronghold"])

    async def run():
        async with AsyncExitStack() as stack:
            await transports.open_session(stack, config, 1, auth=object())

    asyncio.run(run())
    factory = transport_options["httpx_client_factory"]
    assert isinstance(factory, partial) and factory.func is transports._origin_client
    assert factory.args == ("http://stronghold.test/mcp",)
