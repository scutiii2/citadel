"""Stronghold's generated keys and its calls to Portcullis's internal API."""

import asyncio

import httpx
import pytest

from src.keys import load_keys
from src.platform import PlatformError, PortcullisClient
from src.secret_box import SecretBox


def test_keys_are_made_once_and_then_reused(tmp_path) -> None:
    first = load_keys(tmp_path / "data")
    assert load_keys(tmp_path / "data") == first
    assert SecretBox(first.secrets).decrypt_map(SecretBox(first.secrets).encrypt_map({"url": "x"})) == {"url": "x"}
    assert len(first.vapid_public) > 60


def test_a_damaged_keys_file_is_an_error_not_a_silent_replacement(tmp_path) -> None:
    (tmp_path / "keys.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not a valid keys file"):
        load_keys(tmp_path)
    assert (tmp_path / "keys.json").read_text(encoding="utf-8") == "{broken"


def platform(handler) -> PortcullisClient:
    client = httpx.AsyncClient(base_url="http://portcullis.test", transport=httpx.MockTransport(handler))
    return PortcullisClient(client, "internal")


def test_recipient_sends_the_token_and_maps_404_to_none() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "/u-gone/" in request.url.path:
            return httpx.Response(404, json={"detail": "No such recipient"})
        return httpx.Response(200, json={"uid": "u-1", "email": "ana@example.com"})

    api = platform(handler)
    assert asyncio.run(api.recipient("u-1", "calendar.use")) == {"uid": "u-1", "email": "ana@example.com"}
    assert asyncio.run(api.recipient("u-gone", "calendar.use")) is None
    assert seen[0].headers["x-internal-token"] == "internal"
    assert str(seen[0].url) == "http://portcullis.test/internal/accounts/u-1/recipient?permission=calendar.use"


def test_refusals_and_outages_are_platform_errors_but_error_reports_never_raise() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(PlatformError):
        asyncio.run(platform(lambda request: httpx.Response(401)).switches())
    with pytest.raises(PlatformError):
        asyncio.run(platform(down).notify("u-1", "s", "b"))
    asyncio.run(platform(down).report_error("calendar", "x"))


def test_action_log_names_the_account_and_never_raises() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    asyncio.run(platform(handler).log_action("u-1", "memory.create", "Saved a memory"))
    assert (seen[0].method, seen[0].url.path) == ("POST", "/internal/accounts/u-1/actions")
    asyncio.run(platform(down).log_action("u-1", "memory.create", "Saved a memory"))
    asyncio.run(platform(lambda request: httpx.Response(404)).log_action("u-1", "memory.create", "x"))


def test_uids_in_request_lines_are_redacted() -> None:
    import logging

    from src.log_privacy import UidLogFilter

    record = logging.LogRecord("httpx", logging.INFO, "", 0, "HTTP Request: %s %s", (
        "GET", "http://portcullis:29601/internal/accounts/abc123/recipient?permission=calendar.use"), None)
    UidLogFilter().filter(record)
    assert record.getMessage() == "HTTP Request: GET http://portcullis:29601/internal/accounts/[redacted]/recipient?permission=calendar.use"
