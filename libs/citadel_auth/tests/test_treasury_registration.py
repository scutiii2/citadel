"""A service registers its own instance with Treasury and retries until Treasury answers."""

import httpx

from citadel_auth import treasury


def serve(monkeypatch, answers):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.content))
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer)

    monkeypatch.setattr(
        treasury, "service_client",
        lambda keyring, audience, **kwargs: httpx.AsyncClient(transport=httpx.MockTransport(handler), **kwargs))
    return seen


async def test_it_puts_the_instance_with_its_connections(monkeypatch):
    seen = serve(monkeypatch, [200])

    assert await treasury.register_instance(None, "http://t", "ember", ["data", "data"], delay=0) is True
    assert seen == [("PUT", "/instances/ember", b'{"connections":["data"]}')]


async def test_it_retries_while_treasury_is_not_up(monkeypatch):
    seen = serve(monkeypatch, [httpx.ConnectError("down"), 503, 200])

    assert await treasury.register_instance(None, "http://t", "legion", ["data"], delay=0) is True
    assert len(seen) == 3


async def test_a_refusal_is_final(monkeypatch):
    seen = serve(monkeypatch, [403, 200])

    assert await treasury.register_instance(None, "http://t", "armory", ["data"], delay=0) is False
    assert len(seen) == 1


async def test_it_gives_up_after_the_attempts(monkeypatch):
    seen = serve(monkeypatch, [503, 503])

    assert await treasury.register_instance(None, "http://t", "x", ["a"], attempts=2, delay=0) is False
    assert len(seen) == 2
