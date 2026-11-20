import asyncio
from types import SimpleNamespace

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
