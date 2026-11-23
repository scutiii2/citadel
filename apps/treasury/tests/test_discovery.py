# apps/treasury/tests/test_discovery.py
import asyncio

import httpx

from src import discovery, service_catalog


def make_client(up_hosts):
    def handler(request):
        if request.url.host in up_hosts:
            return httpx.Response(200, json={"status": "ok"})
        raise httpx.ConnectError("down", request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def run_discovery(db, up_hosts):
    async with make_client(up_hosts) as client:
        return await discovery.discover(db, client)


def test_it_registers_reachable_services_and_reports_the_rest(tmp_path):
    db = tmp_path / "catalog.db"
    result = asyncio.run(run_discovery(db, {"stronghold", "legion"}))
    assert set(result["registered"]) == {"stronghold", "legion"}
    assert "armory" in result["missed"]
    assert set(service_catalog.effective(db)) >= {"stronghold", "legion"}


def test_a_pin_is_never_overwritten(tmp_path):
    db = tmp_path / "catalog.db"
    service_catalog.pin(db, "stronghold", "http://custom-host:9999")
    asyncio.run(run_discovery(db, {"stronghold"}))
    assert service_catalog.effective(db)["stronghold"] == "http://custom-host:9999"


def test_a_registered_address_is_kept(tmp_path):
    db = tmp_path / "catalog.db"
    service_catalog.register(db, "legion", "http://legion-two:1234")
    result = asyncio.run(run_discovery(db, {"legion"}))
    assert "legion" not in result["registered"]
    assert service_catalog.effective(db)["legion"] == "http://legion-two:1234"


def test_a_manual_registration_during_a_probe_wins(tmp_path):
    db = tmp_path / "catalog.db"

    async def handler(request):
        if request.url.host == "armory":
            await asyncio.to_thread(service_catalog.register, db, "armory", "http://manual:9000")
            return httpx.Response(200)
        return httpx.Response(503)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await discovery.discover(db, client)

    result = asyncio.run(run())
    assert "armory" in result["found"]
    assert "armory" not in result["registered"]
    assert service_catalog.effective(db)["armory"] == "http://manual:9000"
