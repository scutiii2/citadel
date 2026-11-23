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
    monkeypatch.setenv("TREASURY_URL", "http://treasury.test:29602/")
    settings.reset_cache()
    yield fake
    settings.reset_cache()


def test_reads_the_record_with_the_internal_token(treasury):
    treasury.doc = {"url": "http://gateway.test:29407/", "token": "cg_saved"}
    assert settings.current_sync() == settings.GatewaySettings("http://gateway.test:29407", "cg_saved")
    sent = treasury.requests[0]
    assert str(sent.url) == ("http://treasury.test:29602/instances/legion/connections/data"
                             "/collections/legion_settings/records/conversation_gateway")
    import jwt
    from src.runtime import internal_auth
    assert jwt.decode(sent.headers["Authorization"][7:], internal_auth.keyring.private_key.public_key(),
                      algorithms=["EdDSA"], audience="treasury")["iss"] == "legion"


def test_the_default_address_fills_what_the_record_lacks_and_no_environment_variable_names_a_gateway(treasury, monkeypatch):
    monkeypatch.setenv("CONVERSATION_GATEWAY_URL", "http://ignored:1")
    monkeypatch.setenv("CONVERSATION_GATEWAY_TOKEN", "ignored")
    treasury.doc = {"token": "cg_saved"}
    assert asyncio.run(settings.current()) == settings.GatewaySettings(settings.DEFAULT_URL, "cg_saved")


def test_no_record_gives_the_defaults(treasury):
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
    settings._cache[settings.KEY] = (settings._cache[settings.KEY][0], 0.0)  # the cache has expired
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
    {"token": 5}, {"password": "x"}, {"description": "x" * 501}, {"description": None},
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
        "url": "http://gateway.test:29407", "has_token": True, "description": ""}


def test_routes_read_and_save_without_showing_the_token(treasury):
    from starlette.testclient import TestClient

    from src import server

    client = TestClient(server.mcp.streamable_http_app())
    assert client.get("/agents/gateway-settings").json() == {"url": settings.DEFAULT_URL, "has_token": False, "description": ""}
    response = client.put("/agents/gateway-settings", json={"url": "http://gateway.test:29407", "token": "cg_new"})
    assert response.status_code == 200
    assert response.json() == {"url": "http://gateway.test:29407", "has_token": True, "description": ""}
    assert treasury.doc == {"url": "http://gateway.test:29407", "token": "cg_new"}
    refused = client.put("/agents/gateway-settings", json={"url": "nope"})
    assert refused.status_code == 400 and "http(s)" in refused.json()["error"]


def test_the_decision_gateway_has_its_own_record(treasury):
    which = settings.DECISION_KEY
    assert settings.current_sync(which) == settings.GatewaySettings("http://127.0.0.1:29406", "")
    assert str(treasury.requests[0].url).endswith("/records/decision_gateway")
    saved = asyncio.run(settings.save({"token": "dg_new"}, which))
    assert saved == settings.GatewaySettings("http://127.0.0.1:29406", "dg_new")
    assert str(treasury.requests[-1].url).endswith("/records/decision_gateway")
    assert settings._fresh(settings.KEY) is None  # the other service's cache is untouched


@pytest.mark.parametrize("which", [settings.KEY, settings.DECISION_KEY])
def test_description_edit_preserves_legacy_url_and_token(treasury, which):
    treasury.doc = {"url": "https://old.test", "token": "saved"}
    assert asyncio.run(settings.current(which)).description == ""
    saved = asyncio.run(settings.save({"description": "  Model provider  "}, which))
    assert settings.view(saved) == {"url": "https://old.test", "description": "Model provider", "has_token": True}
    assert asyncio.run(settings.save({"url": "https://new.test"}, which)).description == "Model provider"
    assert asyncio.run(settings.save({"description": ""}, which)).description == ""
    assert treasury.doc == {"url": "https://new.test", "token": "saved", "description": ""}


def test_overlapping_partial_edits_merge_after_a_failed_save(treasury, monkeypatch):
    async def delayed_read(which):
        doc = await _read(which)
        await asyncio.sleep(0)
        return doc

    monkeypatch.setattr(settings, "_read", delayed_read)
    treasury.doc = {"url": "https://old.test", "token": "saved"}

    async def edits():
        treasury.down = True
        with pytest.raises(settings.GatewaySettingsError):
            await settings.save({"description": "Never saved"})
        treasury.down = False
        await asyncio.gather(
            settings.save({"description": "Model provider"}),
            settings.save({"url": "https://new.test"}),
        )

    asyncio.run(edits())
    assert treasury.doc == {"url": "https://new.test", "token": "saved", "description": "Model provider"}
