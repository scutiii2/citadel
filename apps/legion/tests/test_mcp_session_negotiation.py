"""open_negotiated: probe for the 2026 protocol, fall back to a fresh handshake session."""
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

from mcp.shared.exceptions import MCPError
from mcp_types import METHOD_NOT_FOUND

from src.tools.mcp_client import transports


def run(monkeypatch, discover_error, probe, built=None):
    log = []

    @asynccontextmanager
    async def streams():
        log.append("open")
        try:
            yield None, None
        finally:
            log.append("close")

    class Session:
        def __init__(self, *args, **kwargs):
            if built is not None:
                built.append("elicitation_callback" in kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def discover(self):
            log.append("discover")
            if discover_error:
                raise discover_error

        async def initialize(self):
            log.append("initialize")

    monkeypatch.setattr(transports, "ClientSession", Session)

    async def go():
        async with AsyncExitStack() as stack:
            await transports.open_negotiated(stack, streams, 1, probe=probe)
            log.append("ready")

    asyncio.run(go())
    return log


def test_a_new_server_keeps_the_discovered_session(monkeypatch):
    assert run(monkeypatch, None, True) == ["open", "discover", "ready", "close"]


def test_an_older_server_gets_a_fresh_handshake_session(monkeypatch):
    refused = MCPError(METHOD_NOT_FOUND, "Method not found")
    assert run(monkeypatch, refused, True) == ["open", "discover", "close", "open", "initialize", "ready", "close"]


def test_an_internal_server_is_not_probed(monkeypatch):
    assert run(monkeypatch, None, False) == ["open", "initialize", "ready", "close"]


def test_only_the_probed_session_declares_elicitation(monkeypatch):
    built = []
    run(monkeypatch, MCPError(METHOD_NOT_FOUND, "Method not found"), True, built)
    assert built == [True, False]
