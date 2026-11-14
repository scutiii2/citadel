"""ConversationGateway's address and token, kept in Treasury and edited by an admin."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from src.runtime import gateway_settings as settings

# conftest replaces the readers for every test; these tests check the real ones.
_read, _read_sync = settings._read, settings._read_sync


class FakeTreasury:
    """One record, behind Treasury's record routes."""

    def __init__(self, doc=None, down=False):
        self.doc, self.down, self.requests = doc, down, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        if request.method == "PUT":
            self.doc = json.loads(request.content)["doc"]
            return httpx.Response(200, json={"ok": True})
        if self.doc is None:
            return httpx.Response(404, json={"error": "no record 'conversation_gateway' in 'legion_settings'"})
        return httpx.Response(200, json={"doc": self.doc})


@pytest.fixture
def treasury(monkeypatch):
    fake = FakeTreasury()
    monkeypatch.setattr(settings, "_read", _read)
    monkeypatch.setattr(settings, "_read_sync", _read_sync)
    monkeypatch.setattr(settings, "_TRANSPORT", httpx.MockTransport(fake))
    monkeypatch.setattr(settings, "_SYNC_TRANSPORT", httpx.MockTransport(fake))
    monkeypatch.setenv("DB_GATEWAY_URL", "http://treasury.test:29602/")
    monkeypatch.setenv("INTERNAL_API_TOKEN", "internal")
    monkeypatch.delenv("CONVERSATION_GATEWAY_URL", raising=False)
    monkeypatch.delenv("CONVERSATION_GATEWAY_TOKEN", raising=False)
    settings.reset_cache()
    yield fake
    settings.reset_cache()


def test_reads_the_record_with_the_internal_token(treasury):
    treasury.doc = {"url": "http://gateway.test:29407/", "token": "cg_saved"}
    assert settings.current_sync() == settings.GatewaySettings("http://gateway.test:29407", "cg_saved")
    sent = treasury.requests[0]
    assert str(sent.url) == ("http://treasury.test:29602/instances/legion/connections/data"
                             "/collections/legion_settings/records/conversation_gateway")
    assert sent.headers["x-internal-token"] == "internal"


def test_the_environment_fills_what_the_record_lacks(treasury, monkeypatch):
    monkeypatch.setenv("CONVERSATION_GATEWAY_URL", "http://conversationgateway:29407")
    monkeypatch.setenv("CONVERSATION_GATEWAY_TOKEN", "cg_env")
    assert settings.current_sync() == settings.GatewaySettings("http://conversationgateway:29407", "cg_env")
    settings.reset_cache()
    treasury.doc = {"token": "cg_saved"}
    assert asyncio.run(settings.current()) == settings.GatewaySettings("http://conversationgateway:29407", "cg_saved")


def test_no_record_and_no_environment_gives_the_defaults(treasury):
    assert settings.current_sync() == settings.GatewaySettings(settings.DEFAULT_URL, "")


def test_reads_are_cached(treasury):
    treasury.doc = {"url": "http://gateway.test:29407"}
    settings.current_sync()
    asyncio.run(settings.current())
    assert len(treasury.requests) == 1


def test_an_outage_keeps_the_last_known_values(treasury):
    treasury.doc = {"url": "http://gateway.test:29407", "token": "cg_saved"}
    settings.current_sync()
    treasury.down = True
    settings._cached_until = 0.0  # the cache has expired
    assert settings.current_sync().token == "cg_saved"


def test_save_keeps_the_token_when_only_the_url_changes(treasury):
    treasury.doc = {"url": "http://old.test:29407", "token": "cg_saved"}
    saved = asyncio.run(settings.save({"url": "https://new.test:29407/"}))
    assert saved == settings.GatewaySettings("https://new.test:29407", "cg_saved")
    assert treasury.doc == {"url": "https://new.test:29407", "token": "cg_saved"}
    assert settings.current_sync() == saved  # the saving process sees it at once


def test_save_an_empty_token_clears_it(treasury):
    treasury.doc = {"url": "http://gateway.test:29407", "token": "cg_saved"}
    assert asyncio.run(settings.save({"token": ""})).token == ""
    assert treasury.doc == {"url": "http://gateway.test:29407", "token": ""}


@pytest.mark.parametrize("changes", [
    {"url": "ftp://gateway.test"}, {"url": ""}, {"url": "http://user:pw@gateway.test"},
    {"url": "http://gateway.test/?a=1"}, {"token": "has space"}, {"token": "x" * 513},
    {"token": 5}, {"password": "x"},
])
def test_save_refuses_bad_values_and_writes_nothing(treasury, changes):
    with pytest.raises(settings.GatewaySettingsError):
        asyncio.run(settings.save(changes))
    assert all(request.method != "PUT" for request in treasury.requests)


def test_save_fails_clearly_when_treasury_is_down(treasury):
    treasury.down = True
    with pytest.raises(settings.GatewaySettingsError, match="not saved"):
        asyncio.run(settings.save({"url": "http://gateway.test:29407"}))


def test_the_view_never_carries_the_token():
    assert settings.view(settings.GatewaySettings("http://gateway.test:29407", "cg_secret")) == {
        "url": "http://gateway.test:29407", "has_token": True}


def test_routes_read_and_save_without_showing_the_token(treasury):
    from starlette.testclient import TestClient

    from src import server

    client = TestClient(server.mcp.streamable_http_app())
    assert client.get("/agents/gateway-settings").json() == {"url": settings.DEFAULT_URL, "has_token": False}
    response = client.put("/agents/gateway-settings", json={"url": "http://gateway.test:29407", "token": "cg_new"})
    assert response.status_code == 200
    assert response.json() == {"url": "http://gateway.test:29407", "has_token": True}
    assert treasury.doc == {"url": "http://gateway.test:29407", "token": "cg_new"}
    refused = client.put("/agents/gateway-settings", json={"url": "nope"})
    assert refused.status_code == 400 and "http(s)" in refused.json()["error"]
