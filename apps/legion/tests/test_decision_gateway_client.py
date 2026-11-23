"""Legion's calls to the built-in DecisionGateway, and the two saved gateways it asks."""

from __future__ import annotations

import pytest

from src import gateway
from src.gateway.decision.errors import GatewayError
from src.providers.decision import gateway_client as client
from src.providers.decision.contract import DecisionError, DecisionRequest
from src.providers.decision.gateways import saved

# conftest replaces the listing for every test; these tests check the real one.
_saved_gateways = client.saved_gateways

QUESTION = {"q": {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}}}
ANSWER = {"q": {"type": "choice", "choice": "a", "answer_confidence": 0.95, "uncertain": False}}


class FakeService:
    def __init__(self):
        self.reply = {"gateway": "laya", "model": "m", "answers": ANSWER, "tokens": 5}
        self.error: GatewayError | None = None
        self.listed: list[dict] = []
        self.requests, self.listings = [], 0

    async def decide(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.reply

    async def gateways(self):
        self.listings += 1
        if self.error:
            raise self.error
        return self.listed


@pytest.fixture
def service(monkeypatch):
    fake = FakeService()
    monkeypatch.setattr(gateway, "decision_service", lambda: fake)
    monkeypatch.setattr(client, "saved_gateways", _saved_gateways)
    client.reset_cache()
    yield fake
    client.reset_cache()


def test_decide_sends_the_saved_gateway_id_and_minimum(service):
    result = saved.laya().ask(DecisionRequest("hi", QUESTION, min_confidence=0.8), timeout=2)
    sent = service.requests[0]
    assert (sent.gateway, sent.text, sent.min_confidence, sent.trace) == ("laya", "hi", 0.8, True)
    assert (result.answers, result.tokens, result.model) == (ANSWER, 5, "m")


def test_no_minimum_leaves_the_threshold_to_the_gateway(service):
    saved.jev().ask(DecisionRequest("hi", QUESTION))
    assert service.requests[0].gateway == "jev" and service.requests[0].min_confidence is None


def test_a_refusal_carries_the_gateway_message_only(service):
    service.error = GatewayError(502, "upstream_unreachable", "The gateway is unreachable.")
    with pytest.raises(DecisionError, match="The gateway is unreachable."):
        saved.jev().ask(DecisionRequest("hi", QUESTION))


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
    assert service.listings == 1


def test_a_failing_listing_means_nothing_is_usable_and_is_not_cached(service):
    service.error = GatewayError(500, "failed", "x")
    assert saved.laya().available() is False
    assert client.is_reachable("laya") is False
    assert service.listings == 2
