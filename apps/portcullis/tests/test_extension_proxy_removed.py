"""Plan 22c: Portcullis no longer proxies Armory's extensions or connection records."""

from __future__ import annotations

import pytest

from src.services.mcp_server_info import McpServerInfo
from tests.test_registration import as_admin


@pytest.mark.parametrize("method, path", [
    ("GET", "/api/extensions"), ("POST", "/api/extensions"), ("DELETE", "/api/extensions/x"),
    ("GET", "/api/admin/connections"), ("PATCH", "/api/admin/connections/bard"), ("DELETE", "/api/admin/connections/x"),
])
def test_the_extension_and_connection_proxy_routes_are_gone(client, method, path):
    as_admin(client)
    assert client.request(method, path, json={}).status_code in (404, 405)


def test_the_server_info_service_has_no_extension_methods():
    assert not hasattr(McpServerInfo, "extensions")
    assert not hasattr(McpServerInfo, "add_extension")
    assert not hasattr(McpServerInfo, "remove_extension")


def test_connection_status_still_works(client):
    as_admin(client)
    assert client.get("/api/connection-status").status_code in (200, 503)
