"""SecurityMiddleware: the outside IP lists apply to /api/outside/ paths only."""

from __future__ import annotations

import asyncio

from src.config import SecuritySettings
from src.security import SecurityMiddleware


def call(settings: SecuritySettings, path: str, ip: str) -> int:
    """One request through SecurityMiddleware around a trivial app; the status."""
    sent: list[dict] = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "path": path, "client": (ip, 1234), "headers": []}
    asyncio.run(SecurityMiddleware(app, settings)(scope, None, send))
    return sent[0]["status"]


def test_the_main_allow_list_does_not_apply_to_outside_paths():
    config = SecuritySettings(ip_allow_list=("192.168.0.0/16",))
    assert call(config, "/api/chats", "203.0.113.5") == 403
    assert call(config, "/api/outside/legion/ask", "203.0.113.5") != 403


def test_the_main_deny_list_still_applies_to_outside_paths():
    config = SecuritySettings(ip_deny_list=("203.0.113.5",))
    assert call(config, "/api/outside/legion/ask", "203.0.113.5") == 403


def test_the_outside_lists_apply_only_to_outside_paths():
    config = SecuritySettings(outside_ip_allow_list=("203.0.113.0/24",), outside_ip_deny_list=("203.0.113.9",))
    assert call(config, "/api/outside/legion/ask", "203.0.113.5") != 403
    assert call(config, "/api/outside/legion/ask", "198.51.100.1") == 403
    assert call(config, "/api/outside/legion/ask", "203.0.113.9") == 403
    assert call(config, "/api/chats", "198.51.100.1") != 403


def test_no_lists_means_everything_is_allowed_as_before():
    assert call(SecuritySettings(), "/api/outside/legion/ask", "198.51.100.1") != 403
    assert call(SecuritySettings(), "/api/chats", "198.51.100.1") != 403
