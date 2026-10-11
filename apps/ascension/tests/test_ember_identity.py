import asyncio
import json
import httpx
import pytest
from src.ember_identity import EmberIdentity, IdentityUnavailable


def call(handler):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
            return await EmberIdentity(client, "http://ember:8030/", "test-internal", "ascension").redeem("one-time")
    return asyncio.run(go())


def test_redeem_posts_exact_contract_and_returns_account_id():
    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == "http://ember:8030/internal/games/tickets/redeem"
        assert request.headers["X-Internal-Token"] == "test-internal"
        assert json.loads(request.content) == {"ticket": "one-time", "game_id": "ascension"}
        assert request.extensions["timeout"]["read"] == 5.0
        return httpx.Response(200, json={"account_id": "42", "display_name": "Player"})
    assert call(handler) == "42"


def test_bad_ticket_returns_none():
    assert call(lambda r: httpx.Response(401, json={"detail": "Invalid ticket"})) is None


@pytest.mark.parametrize("status", [500, 503, 302, 403])
def test_unexpected_status_is_unavailable_and_redirects_are_not_followed(status):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(status, headers={"location": "http://elsewhere/"})
    with pytest.raises(IdentityUnavailable):
        call(handler)
    assert len(seen) == 1


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_transport_failure_is_unavailable(error):
    def handler(request):
        raise error("private diagnostic", request=request)
    with pytest.raises(IdentityUnavailable):
        call(handler)


@pytest.mark.parametrize("payload", [{}, [], {"account_id": None}, {"account_id": 42}, {"account_id": ""}])
def test_invalid_success_response_is_unavailable(payload):
    with pytest.raises(IdentityUnavailable):
        call(lambda r: httpx.Response(200, json=payload))


def test_non_json_success_is_unavailable():
    with pytest.raises(IdentityUnavailable):
        call(lambda r: httpx.Response(200, content=b"not json"))
