"""Portcullis -> Stronghold: identity and the internal token go across, cookies never do."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from src.services.stronghold_forwarder import StrongholdForwarder, StrongholdUnavailable
from tests.conftest import FakeUpstream
from tests.test_registration import as_admin

ACCOUNT = SimpleNamespace(uid="u-1", username="ana", email="ana@example.com")


def forwarder(upstream: FakeUpstream, token: str | None = "secret-token") -> StrongholdForwarder:
    client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    return StrongholdForwarder(client, "http://stronghold.internal:29650/", token)


def test_sends_identity_and_token():
    upstream = FakeUpstream(handler=lambda request: httpx.Response(200, json={"ok": True}))
    result = asyncio.run(forwarder(upstream).forward("GET", "/whoami", ACCOUNT, params={"a": "1"}))
    sent = upstream.requests[0]
    assert str(sent.url) == "http://stronghold.internal:29650/whoami?a=1"
    assert sent.headers["x-internal-token"] == "secret-token"
    assert sent.headers["x-requester-uid"] == "u-1"
    assert sent.headers["x-requester-username"] == "ana"
    assert sent.headers["x-requester-email"] == "ana@example.com"
    assert "cookie" not in sent.headers and "authorization" not in sent.headers
    assert (result.status, result.body, result.content_type) == (200, b'{"ok":true}', "application/json")


def test_no_token_header_when_none_is_configured():
    upstream = FakeUpstream(handler=lambda request: httpx.Response(200, json={}))
    asyncio.run(forwarder(upstream, token=None).forward("GET", "/whoami", ACCOUNT))
    assert "x-internal-token" not in upstream.requests[0].headers


def test_passes_a_refusal_through_unchanged():
    upstream = FakeUpstream(handler=lambda request: httpx.Response(404, json={"detail": "No such note"}))
    result = asyncio.run(forwarder(upstream).forward("GET", "/notes/9", ACCOUNT))
    assert result.status == 404
    assert result.body == b'{"detail":"No such note"}'


def test_sends_a_json_body():
    upstream = FakeUpstream(handler=lambda request: httpx.Response(201, json={"id": 1}))
    asyncio.run(forwarder(upstream).forward("POST", "/notes", ACCOUNT, json={"title": "t"}))
    sent = upstream.requests[0]
    assert sent.content == b'{"title":"t"}'
    assert sent.headers["content-type"] == "application/json"


def test_unreachable_raises():
    upstream = FakeUpstream(unreachable=True)
    with pytest.raises(StrongholdUnavailable):
        asyncio.run(forwarder(upstream).forward("GET", "/whoami", ACCOUNT))


def test_a_server_error_raises():
    upstream = FakeUpstream(handler=lambda request: httpx.Response(500, text="boom"))
    with pytest.raises(StrongholdUnavailable):
        asyncio.run(forwarder(upstream).forward("GET", "/whoami", ACCOUNT))


def stronghold_calls(upstream: FakeUpstream) -> list[httpx.Request]:
    return [request for request in upstream.requests if request.url.path == "/whoami"]


def test_route_forwards_for_a_logged_in_account(client_factory, upstream):
    upstream.handler = lambda request: httpx.Response(200, json={"uid": request.headers["x-requester-uid"]})
    client = as_admin(client_factory(internal_token="secret-token"))
    response = client.get("/api/stronghold/whoami")
    assert response.status_code == 200
    sent = stronghold_calls(upstream)[0]
    assert str(sent.url) == "http://127.0.0.1:29650/whoami"
    assert sent.headers["x-internal-token"] == "secret-token"
    assert sent.headers["x-requester-username"] == "root"
    assert response.json() == {"uid": sent.headers["x-requester-uid"]}
    assert "cookie" not in sent.headers


def test_route_needs_a_login(client, upstream):
    response = client.get("/api/stronghold/whoami")
    assert response.status_code == 401
    assert stronghold_calls(upstream) == []


def test_route_reports_an_outage_as_502(client_factory, upstream):
    client = as_admin(client_factory())
    upstream.unreachable = True
    response = client.get("/api/stronghold/whoami")
    assert response.status_code == 502
    assert response.json() == {"detail": "Stronghold is unavailable"}
