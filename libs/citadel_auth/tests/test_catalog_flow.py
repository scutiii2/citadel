"""Start-order recovery and last-good catalog survival across outages."""
import asyncio

import httpx
from fastapi import FastAPI

from citadel_auth.catalog import CatalogTransport, ServiceCatalog, logical_url
from test_catalog import FakeKeyring


class Treasury:
    def __init__(self, unavailable_calls=0):
        self.services = {}
        self.calls = 0
        self.unavailable_calls = unavailable_calls
        self.failed = False
        self.app = FastAPI()

        @self.app.middleware("http")
        async def ready(request, call_next):
            self.calls += 1
            if self.failed or self.calls <= self.unavailable_calls:
                from fastapi.responses import JSONResponse
                return JSONResponse({}, status_code=500 if self.failed else 503)
            return await call_next(request)

        @self.app.put("/services/{name}")
        async def register(name: str, body: dict):
            self.services[name] = body["url"]
            return {"saved": name}

        @self.app.get("/services")
        async def services():
            return {"services": dict(self.services)}


class QuickCatalog(ServiceCatalog):
    async def register(self, name, url, **kwargs):
        return await super().register(name, url, attempts=2, delay=0)


def catalogs(tmp_path, treasury):
    return [QuickCatalog(FakeKeyring(), "http://treasury", cache_path=tmp_path / f"{name}.json",
                         interval=0.005, transport=httpx.ASGITransport(app=treasury.app))
            for name in ("stronghold", "armory")]


async def wait_for_peers(peers):
    async with asyncio.timeout(1):
        while peers[0].url("armory") != "http://armory.test:29600" or peers[1].url("stronghold") != "http://stronghold.test:29650":
            await asyncio.sleep(0.005)


def test_services_started_before_treasury_eventually_register_and_route(tmp_path):
    async def go():
        treasury = Treasury(unavailable_calls=8)
        peers = catalogs(tmp_path, treasury)
        peers[0].start("stronghold", "http://stronghold.test:29650")
        peers[1].start("armory", "http://armory.test:29600")
        try:
            await wait_for_peers(peers)
            assert treasury.services == {"stronghold": "http://stronghold.test:29650", "armory": "http://armory.test:29600"}
            seen = []
            def receive(request):
                seen.append(str(request.url))
                return httpx.Response(200)
            async with httpx.AsyncClient(transport=CatalogTransport(peers[0], httpx.MockTransport(receive))) as client:
                assert (await client.get(logical_url("armory") + "/mcp")).status_code == 200
            assert seen == ["http://armory.test:29600/mcp"]
        finally:
            for peer in peers:
                await peer.stop()
    asyncio.run(go())


def test_outage_preserves_addresses_and_restart_uses_disk_cache(tmp_path):
    async def go():
        treasury = Treasury()
        peers = catalogs(tmp_path, treasury)
        peers[0].start("stronghold", "http://stronghold.test:29650")
        peers[1].start("armory", "http://armory.test:29600")
        try:
            await wait_for_peers(peers)
            treasury.failed = True
            assert await peers[0].refresh() is False
            assert await peers[1].refresh() is False
            assert peers[0].url("armory") == "http://armory.test:29600"
            assert peers[1].url("stronghold") == "http://stronghold.test:29650"
            restarted = catalogs(tmp_path, treasury)
            assert restarted[0].url("armory") == "http://armory.test:29600"
            assert restarted[1].url("stronghold") == "http://stronghold.test:29650"
        finally:
            for peer in peers:
                await peer.stop()
    asyncio.run(go())
