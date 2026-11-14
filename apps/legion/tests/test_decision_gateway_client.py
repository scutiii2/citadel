"""Legion's calls to DecisionGateway, and the two saved gateways it asks."""

from __future__ import annotations

import json

import httpx
import pytest

from src.providers.decision import gateway_client as client
from src.providers.decision.contract import DecisionError, DecisionRequest
from src.providers.decision.gateways import saved
from src.runtime import gateway_settings

# conftest replaces the listing for every test; these tests check the real one.
_saved_gateways = client.saved_gateways

QUESTION = {"q": {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}}}
ANSWER = {"q": {"type": "choice", "choice": "a", "answer_confidence": 0.95, "uncertain": False}}


class FakeService:
    def __init__(self, reply=None, status=200, listed=None, down=False):
        self.reply = reply if reply is not None else {"gateway": "laya", "model": "m", "answers": ANSWER, "tokens": 5}
        self.status, self.listed, self.down, self.requests = status, listed, down, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        if request.url.path == "/api/gateways":
            return httpx.Response(200, json={"gateways": self.listed or []})
        return httpx.Response(self.status, json=self.reply)

    def body(self, index=0):
        return json.loads(self.requests[index].content)


@pytest.fixture
def service(monkeypatch):
    fake = FakeService()
    monkeypatch.setattr(client, "_TRANSPORT", httpx.MockTransport(fake))
    monkeypatch.setattr(client, "saved_gateways", _saved_gateways)
    monkeypatch.setattr(client, "_settings",
                        lambda: gateway_settings.GatewaySettings("http://decisiongateway.test:29406", "dg_token"))
    client.reset_cache()
    yield fake
    client.reset_cache()


def test_decide_sends_the_saved_gateway_id_token_and_minimum(service):
    result = saved.laya().ask(DecisionRequest("hi", QUESTION, min_confidence=0.8), timeout=2)
    sent = service.requests[0]
    assert str(sent.url) == "http://decisiongateway.test:29406/api/decide"
    assert sent.headers["x-internal-token"] == "dg_token"
    assert service.body() == {"gateway": "laya", "text": "hi", "questions": QUESTION, "trace": True,
                              "min_confidence": 0.8}
    assert (result.answers, result.tokens, result.model) == (ANSWER, 5, "m")


def test_no_minimum_leaves_the_threshold_to_the_gateway(service):
    saved.jev().ask(DecisionRequest("hi", QUESTION))
    assert "min_confidence" not in service.body() and service.body()["gateway"] == "jev"


def test_a_refusal_carries_the_gateway_message_only(service):
    service.status, service.reply = 502, {"error": "upstream_unreachable", "message": "The gateway is unreachable."}
    with pytest.raises(DecisionError, match="The gateway is unreachable."):
        saved.jev().ask(DecisionRequest("hi", QUESTION))


def test_an_unreachable_service_is_a_decision_error(service):
    service.down = True
    with pytest.raises(DecisionError, match="could not be reached"):
        saved.laya().ask(DecisionRequest("hi", QUESTION))


def test_an_unexpected_reply_is_a_decision_error(service):
    service.reply = {"answers": []}
    with pytest.raises(DecisionError, match="unexpected shape"):
        saved.laya().ask(DecisionRequest("hi", QUESTION))


def test_laya_refuses_long_text_before_any_call(service):
    with pytest.raises(DecisionError, match="at most 4000"):
        saved.laya().ask(DecisionRequest("x" * (saved.LAYA_MAX_CHARS + 1), QUESTION))
    assert service.requests == []
    saved.jev().ask(DecisionRequest("x" * (saved.LAYA_MAX_CHARS + 1), QUESTION))  # Jev has no such limit here


def test_laya_is_local_and_jev_is_not():
    assert (saved.laya().local, saved.jev().local) == (True, False)


def test_availability_follows_the_listing_and_is_cached(service):
    service.listed = [{"id": "laya", "reachable": True}, {"id": "jev", "reachable": False}, {"id": "spare"}]
    assert saved.laya().available() is True
    assert saved.jev().available() is False       # saved, but its upstream is down
    assert client.is_usable("spare") is True      # saved, not probed
    assert client.is_usable("missing") is False   # not saved
    assert client.is_reachable("laya") is True and client.is_reachable("spare") is False
    assert len(service.requests) == 1


def test_an_unreachable_service_counts_as_usable_but_never_as_reachable(service):
    """The ask itself then reports the outage, so `both` can still fall through."""
    service.down = True
    assert saved.laya().available() is True
    assert client.is_reachable("laya") is False
    assert len(service.requests) == 2  # an outage is not cached


def test_routes_read_and_save_the_decision_gateway_settings(monkeypatch):
    from starlette.testclient import TestClient

    from src import server

    stored: dict = {}

    async def read(which=None):
        return dict(stored)

    async def save(changes, which):
        assert which == gateway_settings.DECISION_KEY
        stored.update(changes)
        return gateway_settings.GatewaySettings(stored.get("url", ""), stored.get("token", ""))

    monkeypatch.delenv("DECISION_GATEWAY_URL", raising=False)
    monkeypatch.setattr(gateway_settings, "_read", read)
    monkeypatch.setattr(gateway_settings, "save", save)
    gateway_settings.reset_cache()
    http = TestClient(server.mcp.streamable_http_app())
    assert http.get("/agents/decision-gateway-settings").json() == {"url": "http://127.0.0.1:29406", "has_token": False}
    response = http.put("/agents/decision-gateway-settings", json={"url": "http://dg.test:29406", "token": "dg_new"})
    assert response.json() == {"url": "http://dg.test:29406", "has_token": True}
    gateway_settings.reset_cache()
