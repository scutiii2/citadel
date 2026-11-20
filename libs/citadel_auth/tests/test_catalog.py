# libs/citadel_auth/tests/test_catalog.py
import asyncio
import json

import httpx
import pytest

from citadel_auth.catalog import (
    DEFAULTS, CatalogTransport, ServiceCatalog, UnknownService, advertised_url, checked_address, logical_url, resolved,
)


class FakeKeyring:
    service = "stronghold"
    private_key = __import__("cryptography.hazmat.primitives.asymmetric.ed25519", fromlist=["Ed25519PrivateKey"]).Ed25519PrivateKey.generate()
    kid = "catalog-test"

    async def ensure_identity(self):
        return None


@pytest.fixture(autouse=True)
def _no_advertise_env(monkeypatch):
    monkeypatch.delenv("CITADEL_ADVERTISE_URL", raising=False)


def make(handler, tmp_path, *, outside_handler=None, **options):
    def dispatch(request):
        if request.url.path == "/outside":
            return outside_handler(request) if outside_handler else httpx.Response(404)
        return handler(request)

    return ServiceCatalog(
        FakeKeyring(), "http://treasury.test:29602", cache_path=tmp_path / "catalog.json",
        transport=httpx.MockTransport(dispatch), **options,
    )


def test_checked_address_accepts_a_base_and_trims_the_slash():
    assert checked_address(" http://armory:29600/ ") == "http://armory:29600"


@pytest.mark.parametrize("bad", ["", "ftp://x", "http://", "http://u:p@h", "http://h/path", "http://h?x=1", "http://h#f", None, 5])
def test_checked_address_refuses_anything_else(bad):
    with pytest.raises(ValueError):
        checked_address(bad)


def test_advertised_url_prefers_env_then_config_then_host_and_port(monkeypatch):
    assert advertised_url("0.0.0.0", 29650) == "http://127.0.0.1:29650"
    assert advertised_url("127.0.0.1", 29650) == "http://127.0.0.1:29650"
    assert advertised_url("0.0.0.0", 29650, "http://stronghold:29650/") == "http://stronghold:29650"
    monkeypatch.setenv("CITADEL_ADVERTISE_URL", "http://from-env:1")
    assert advertised_url("0.0.0.0", 29650, "http://stronghold:29650") == "http://from-env:1"


def test_resolved_calls_a_callable_and_passes_a_string_through():
    assert resolved("http://a") == "http://a"
    assert resolved(lambda: "http://b") == "http://b"


def test_url_falls_back_to_the_defaults_and_treasury_is_the_bootstrap_address(tmp_path):
    catalog = make(lambda request: httpx.Response(500), tmp_path)
    assert catalog.url("armory") == DEFAULTS["armory"]
    assert catalog.url("treasury") == "http://treasury.test:29602"
    assert catalog.mcp_url() == DEFAULTS["armory"] + "/mcp"
    with pytest.raises(UnknownService):
        catalog.url("bard")


def test_refresh_reads_the_catalog_keeps_it_and_writes_the_cache(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"services": {"armory": "http://armory:29600", "bard": "http://evil:1", "legion": "nonsense"}})

    catalog = make(handler, tmp_path)
    assert asyncio.run(catalog.refresh()) is True
    assert seen["url"] == "http://treasury.test:29602/services"
    assert seen["auth"].startswith("Bearer ")
    assert catalog.url("armory") == "http://armory:29600"
    assert catalog.url("legion") == DEFAULTS["legion"]  # an invalid entry is ignored
    assert json.loads((tmp_path / "catalog.json").read_text())["armory"] == "http://armory:29600"


def test_a_new_catalog_starts_from_the_cache_when_treasury_is_down(tmp_path):
    (tmp_path / "catalog.json").write_text(json.dumps({"armory": "http://cached:29600"}))
    catalog = make(lambda request: httpx.Response(503), tmp_path)
    assert catalog.url("armory") == "http://cached:29600"
    assert asyncio.run(catalog.refresh()) is False
    assert catalog.url("armory") == "http://cached:29600"  # a failed refresh keeps what it had


def test_an_unreadable_cache_is_ignored(tmp_path):
    (tmp_path / "catalog.json").write_text("{not json")
    assert make(lambda request: httpx.Response(500), tmp_path).url("armory") == DEFAULTS["armory"]


def test_register_retries_while_treasury_is_not_ready_then_succeeds(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        return httpx.Response(503 if len(calls) < 3 else 200, json={"saved": "stronghold"})

    catalog = make(handler, tmp_path)
    assert asyncio.run(catalog.register("stronghold", "http://stronghold:29650", attempts=5, delay=0)) is True
    assert calls[-1] == ("PUT", "/services/stronghold", {"url": "http://stronghold:29650"})
    assert len(calls) == 3


def test_register_gives_up_on_a_refusal_without_retrying(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(403, json={"error": "no"})

    assert asyncio.run(make(handler, tmp_path).register("stronghold", "http://x:1", attempts=5, delay=0)) is False
    assert len(calls) == 1


def test_transport_swaps_a_logical_host_for_the_catalog_address(tmp_path):
    catalog = make(lambda request: httpx.Response(500), tmp_path)
    catalog._known["stronghold"] = "https://stronghold.internal:8443"
    seen = {}

    def inner(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["host"] = request.headers["host"]
        return httpx.Response(200)

    async def go():
        async with httpx.AsyncClient(base_url=logical_url("stronghold"), transport=CatalogTransport(catalog, httpx.MockTransport(inner))) as client:
            return await client.get("/chats?limit=1")

    assert asyncio.run(go()).status_code == 200
    assert seen == {"url": "https://stronghold.internal:8443/chats?limit=1", "host": "stronghold.internal:8443"}


def test_transport_leaves_other_hosts_alone(tmp_path):
    catalog = make(lambda request: httpx.Response(500), tmp_path)
    seen = {}

    def inner(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200)

    async def go():
        async with httpx.AsyncClient(transport=CatalogTransport(catalog, httpx.MockTransport(inner))) as client:
            await client.get("http://bard.test:29400/health")

    asyncio.run(go())
    assert seen["url"] == "http://bard.test:29400/health"


def test_start_registers_then_refreshes_and_stop_cancels(tmp_path):
    state = {"puts": 0, "gets": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            state["puts"] += 1
            return httpx.Response(200, json={"saved": "stronghold"})
        state["gets"] += 1
        return httpx.Response(200, json={"services": {"armory": "http://armory:29600"}})

    async def go():
        catalog = make(handler, tmp_path, interval=0.01)
        catalog.start("stronghold", "http://stronghold:29650")
        for _ in range(100):
            if state["gets"] >= 2:
                break
            await asyncio.sleep(0.01)
        await catalog.stop()
        return catalog

    catalog = asyncio.run(go())
    assert state["puts"] == 1 and state["gets"] >= 2
    assert catalog.url("armory") == "http://armory:29600"


def test_logical_connection_failure_wakes_catalog_refresh(tmp_path):
    catalog = make(lambda request: httpx.Response(500), tmp_path)
    async def go():
        catalog._wake = asyncio.Event()
        def down(request):
            raise httpx.ConnectError("down", request=request)
        async with httpx.AsyncClient(transport=CatalogTransport(catalog, httpx.MockTransport(down))) as client:
            with pytest.raises(httpx.ConnectError):
                await client.get(logical_url("portcullis") + "/internal/accounts/u/permissions")
        assert catalog._wake.is_set()
    asyncio.run(go())


@pytest.mark.parametrize("bad", ["http://@host", "http://host:bad", "http://host:99999", "http://host:", "http://ho st", "http://host//", "http://host?", "http://host#", "http://ho\nst"])
def test_checked_address_refuses_invalid_origins(bad):
    with pytest.raises(ValueError):
        checked_address(bad)


def test_a_successful_snapshot_removes_an_unpinned_address(tmp_path):
    responses = [{"services": {"armory": "http://pinned:29600"}}, {"services": {}}]
    catalog = make(lambda request: httpx.Response(200, json=responses.pop(0)), tmp_path)
    assert asyncio.run(catalog.refresh()) is True
    assert catalog.url("armory") == "http://pinned:29600"
    assert asyncio.run(catalog.refresh()) is True
    assert catalog.url("armory") == "http://127.0.0.1:29600"


def test_background_refusal_is_final(tmp_path):
    calls = []
    def handler(request):
        if request.method == "PUT":
            calls.append(request.url.path)
            return httpx.Response(403)
        return httpx.Response(200, json={"services": {}})
    async def go():
        catalog = make(handler, tmp_path, interval=0.001)
        catalog.start("stronghold", "http://stronghold:29650")
        await asyncio.sleep(0.02)
        await catalog.stop()
    asyncio.run(go())
    assert calls == ["/services/stronghold"]


def test_advertised_url_brackets_an_ipv6_listener():
    assert advertised_url("::1", 29650) == "http://[::1]:29650"
    assert checked_address(advertised_url("::1", 29650)) == "http://[::1]:29650"


OUTSIDE = {"groups": [{"service_id": "a" * 32, "name": "bard", "used_by": ["legion"],
                       "origins": [{"origin_id": "b" * 32, "origin": "http://bard:29400"},
                                   {"origin_id": "c" * 32, "origin": "http://bard2:29400"}]}]}


def _handler(outside_status=200):
    def handler(request):
        if request.url.path == "/services":
            return httpx.Response(200, json={"services": {}})
        if request.url.path == "/outside":
            return httpx.Response(outside_status, json=OUTSIDE)
        return httpx.Response(404)
    return handler


async def test_refresh_reads_the_outside_groups_and_resolves_origin_ids(tmp_path):
    catalog = make(_handler(), tmp_path, outside_handler=_handler())
    assert await catalog.refresh() is True
    assert catalog.outside_origin("c" * 32) == "http://bard2:29400"
    group = catalog.outside_group("a" * 32)
    assert group["name"] == "bard" and [o["origin"] for o in group["origins"]] == ["http://bard:29400", "http://bard2:29400"]
    assert [g["name"] for g in catalog.outside_groups()] == ["bard"]
    with pytest.raises(UnknownService):
        catalog.outside_origin("0" * 32)


async def test_the_outside_groups_survive_a_restart_through_the_disk_cache(tmp_path):
    await make(_handler(), tmp_path, outside_handler=_handler()).refresh()
    fresh = make(_handler(), tmp_path, outside_handler=_handler(outside_status=500))  # no refresh: only the cache
    assert fresh.outside_origin("b" * 32) == "http://bard:29400"
    assert (await fresh.refresh()) is True  # services answered; a failing /outside changes nothing
    assert fresh.outside_origin("b" * 32) == "http://bard:29400"


async def test_a_treasury_without_outside_still_refreshes(tmp_path):
    catalog = make(_handler(), tmp_path)
    assert await catalog.refresh() is True
    assert catalog.outside_groups() == []


async def test_a_bad_outside_entry_is_dropped(tmp_path):
    bad = {"groups": [{"service_id": "a" * 32, "name": "x", "origins": [{"origin_id": "b" * 32, "origin": "http://u:p@x"}]}, {"nope": 1}]}

    def handler(request):
        return httpx.Response(200, json={"services": {}} if request.url.path == "/services" else bad)

    catalog = make(handler, tmp_path, outside_handler=handler)
    await catalog.refresh()
    assert catalog.outside_groups()[0]["origins"] == []

async def test_outside_groups_are_copied_and_a_successful_empty_snapshot_clears_the_cache(tmp_path):
    groups = iter([OUTSIDE, {"groups": []}])
    catalog = make(_handler(), tmp_path, outside_handler=lambda request: httpx.Response(200, json=next(groups)))
    assert await catalog.refresh() is True
    catalog.outside_groups()[0]["origins"].clear()
    catalog.outside_group("a" * 32)["origins"][0]["origin"] = "http://other"
    assert catalog.outside_origin("b" * 32) == "http://bard:29400"
    assert await catalog.refresh() is True
    assert make(_handler(), tmp_path).outside_groups() == []
    with pytest.raises(UnknownService):
        catalog.outside_group("a" * 32)


async def test_outside_can_refresh_when_access_to_services_is_denied(tmp_path):
    catalog = make(lambda request: httpx.Response(403), tmp_path, outside_handler=_handler())
    assert await catalog.refresh() is False
    assert catalog.outside_origin("b" * 32) == "http://bard:29400"
    assert make(_handler(), tmp_path).outside_origin("b" * 32) == "http://bard:29400"


async def test_services_are_available_and_cached_while_outside_is_still_loading(tmp_path):
    reached_outside = asyncio.Event()
    release_outside = asyncio.Event()

    async def outside(request):
        reached_outside.set()
        await release_outside.wait()
        return httpx.Response(404)

    def services(request):
        return httpx.Response(200, json={"services": {"armory": "http://new-armory:29600"}})

    catalog = make(services, tmp_path, outside_handler=outside)
    refreshing = asyncio.create_task(catalog.refresh())
    try:
        await asyncio.wait_for(reached_outside.wait(), timeout=1)
        assert catalog.url("armory") == "http://new-armory:29600"
        assert make(services, tmp_path).url("armory") == "http://new-armory:29600"
    finally:
        release_outside.set()
        await refreshing
