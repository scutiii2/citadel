from __future__ import annotations

import asyncio

import httpx
import pytest

from src.services.calendar_fetcher import CalendarFetcher, FeedError, clean_feed_url

PUBLIC = ["93.184.216.34"]


async def public(host: str, port: int) -> list[str]:
    return PUBLIC


async def loopback(host: str, port: int) -> list[str]:
    return ["127.0.0.1"]


def fetcher(handler, resolve=public, max_bytes: int = 1000, **kw) -> CalendarFetcher:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return CalendarFetcher(client, max_bytes=max_bytes, resolve=resolve, **kw)


def test_webcal_becomes_https_and_other_links_are_refused() -> None:
    assert clean_feed_url(" webcal://x.com/a.ics ") == "https://x.com/a.ics"
    for bad in ("http://x.com/a.ics", "ftp://x.com", "", "https://u:p@x.com/a"):
        with pytest.raises(FeedError):
            clean_feed_url(bad)


def test_fetch_returns_body_and_etag() -> None:
    f = fetcher(lambda r: httpx.Response(200, content=b"ICS", headers={"etag": '"1"'}))
    got = asyncio.run(f.fetch("https://x.com/a.ics"))
    assert (got.body, got.etag, got.not_modified) == (b"ICS", '"1"', False)


def test_304_is_not_modified_and_the_etag_is_sent() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["inm"] = request.headers.get("if-none-match")
        return httpx.Response(304)

    got = asyncio.run(fetcher(handler).fetch("https://x.com/a.ics", '"1"'))
    assert got.not_modified and seen["inm"] == '"1"'


def test_private_addresses_are_refused_unless_allowed() -> None:
    ok = lambda r: httpx.Response(200, content=b"ICS")  # noqa: E731
    with pytest.raises(FeedError, match="not allowed"):
        asyncio.run(fetcher(ok, resolve=loopback).fetch("https://x.com/a.ics"))
    allowed = fetcher(ok, resolve=loopback, allow_private_urls=True)
    assert asyncio.run(allowed.fetch("https://x.com/a.ics")).body == b"ICS"


def test_a_redirect_to_a_private_host_is_refused() -> None:
    async def resolve(host: str, port: int) -> list[str]:
        return ["127.0.0.1"] if host == "inner.local" else PUBLIC

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "x.com":
            return httpx.Response(302, headers={"location": "https://inner.local/a.ics"})
        return httpx.Response(200, content=b"secret")

    with pytest.raises(FeedError, match="not allowed"):
        asyncio.run(fetcher(handler, resolve=resolve).fetch("https://x.com/a.ics"))


def test_a_redirect_to_http_is_refused() -> None:
    f = fetcher(lambda r: httpx.Response(302, headers={"location": "http://x.com/a.ics"}))
    with pytest.raises(FeedError, match="not https"):
        asyncio.run(f.fetch("https://x.com/a.ics"))


def test_oversized_failed_and_unreachable_feeds_raise_feed_error() -> None:
    with pytest.raises(FeedError, match="too large"):
        asyncio.run(fetcher(lambda r: httpx.Response(200, content=b"x" * 2000)).fetch("https://x.com/a"))
    with pytest.raises(FeedError, match="HTTP 500"):
        asyncio.run(fetcher(lambda r: httpx.Response(500)).fetch("https://x.com/a"))

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(FeedError, match="could not be reached"):
        asyncio.run(fetcher(refuse).fetch("https://x.com/a"))
