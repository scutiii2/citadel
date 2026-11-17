# Plan 13: a service catalog in Treasury Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portcullis, Stronghold, Armory and Legion stop reading each other's addresses from `.env`, config files and admin pages. Each registers its own address with Treasury at start, and every call between them looks the peer up in Treasury's catalog.

**Architecture:** Treasury needs nothing to start, so it holds the catalog (table `service_addresses` in `.data/treasury/settings.db`). The one value a service still needs is where Treasury is: `treasury_url` in its tracked `configs/config_app.json` (env `TREASURY_URL` overrides it, Compose sets it). `citadel_auth` gets a `ServiceCatalog` that registers, refreshes, caches the last good catalog on disk and answers `url(name)` at request time. An administrator can pin an address on a Treasury Admin page. A pin beats a registration, a registration beats a built-in default.

**Tech Stack:** Python 3.11+, FastAPI, httpx, SQLite (`settings_store`), uv and pytest. Vue 3, TypeScript, pnpm, Vitest for the admin page.

**Spec:** none written; the design is the discussion of 2026-11-18 recorded here. Background: `docs/superpowers/plans/2026-11-17-plan-12-dynamic-service-auth-design.md` (signed service calls, trust folders) and `apps/treasury/configs/README.md` (instances, connections).

## Global Constraints

- Never read, print or write `.env*`, `secrets/`, `.secrets/` or key files. Only `.env.example` files may be edited.
- Never add a reduced-motion setting, `prefers-reduced-motion` media query or test (Citadel `AGENTS.md`).
- Python runs through `uv run`; JS through `pnpm` (never `pip`, `npm`).
- Shared library source is `libs/citadel_auth/citadel_auth/`. After every change to it run `uv run scripts/sync_citadel_auth.py` (copies into the five apps' `src/citadel_auth/`) and check with `--check`. Never edit a vendored copy by hand.
- Tests: `uv run pytest -q -p no:cacheprovider` in each app (`-m "not slow"` for Armory and Legion). Portcullis takes about 9 minutes: run it in the background. Admin apps: `pnpm exec vue-tsc -b` and `pnpm exec vitest run`.
- Windows: source files use CRLF. Keep each file's existing line endings. Write edit scripts to files, not heredocs with quotes.
- Only Treasury, Portcullis, Stronghold, Armory and Legion are in the catalog (names in `citadel_auth.policy.SERVICES`). Bard, Scribe, Reader, Lens, Mimic, ConversationGateway, DecisionGateway and Laya keep their address and token set on admin pages. Do not touch them.
- A service may register only its own name. A registered or pinned address is a base address: `http(s)://host[:port]`, no credentials, path, query or fragment. The MCP path `/mcp` is added by the caller.
- Built-in defaults (used until something is registered): `treasury` `http://127.0.0.1:29602`, `portcullis` `http://127.0.0.1:29601`, `stronghold` `http://127.0.0.1:29650`, `armory` `http://127.0.0.1:29600`, `legion` `http://127.0.0.1:29603`.
- Start order must not matter: a service that cannot reach Treasury at start retries in the background and uses its cached catalog, then the defaults.
- A missing or stale catalog entry must fail like a peer that is down (connection error), never crash start-up.

## What changes for each setting

| Setting today | Where it goes |
|---|---|
| Portcullis `config_app.json` `db_gateway.url` (instance, connection stay) | `treasury_url` |
| Stronghold `DB_GATEWAY_URL` / `db_gateway_url` | `treasury_url` |
| Armory `DB_GATEWAY_URL` / `db_gateway_url` (also an editable Armory Settings field) | `treasury_url`; the Settings field is removed |
| Legion Treasury address (saved in `settings.db`, Legion Admin card, `/agents/treasury-address`) | `treasury_url` in new `apps/legion/configs/config_app.json`; the card and routes are removed |
| Portcullis `stronghold_url`, `mcp_server_url` | catalog `stronghold`, `armory` (+ `/mcp`) |
| Stronghold `PORTCULLIS_URL`, `ARMORY_URL` | catalog `portcullis`, `armory` |
| Armory `STRONGHOLD_URL` (also an editable Settings field) | catalog `stronghold`; the Settings field is removed |
| Legion `MCP_SERVER_URL` default for server `main` | catalog `armory` + `/mcp` (a saved server URL still wins) |
| Compose `*_URL` variables | `TREASURY_URL` and `CITADEL_ADVERTISE_URL` per service |

Left alone: `agents_registry_url` / `agents_registry_path` (Legion's agent list), `bard_url`, `scribe_url`, `reader_url`, Laya, Obsidian, Firecrawl.

## File Structure

- `libs/citadel_auth/citadel_auth/catalog.py` (create): `ServiceCatalog`, `CatalogTransport`, `logical_url`, `checked_address`, `advertised_url`, `resolved`, `DEFAULTS`, `UnknownService`.
- `libs/citadel_auth/citadel_auth/__init__.py` (modify): export the new names.
- `libs/citadel_auth/tests/test_catalog.py` (create): library tests.
- `apps/treasury/src/service_catalog.py` (create): the store (registered, pinned, effective view), no HTTP.
- `apps/treasury/src/api.py` (modify): `GET /services`, `PUT /services/{name}`, `GET/PUT/DELETE /admin/services...`.
- `apps/treasury/tests/test_service_catalog.py` (create).
- `apps/portcullis/src/routes/admin_treasury.py` (modify): pass-through of the admin routes.
- `apps/treasury_admin/src/views/ServicesView.vue` and its api, router and test (create/modify).
- Each service's `config`, startup and call sites: listed per task.
- `docker-compose.yml`, `docker/configs/*/app.json`, `.env.example` files, docs.

---

### Task 1: The catalog client in `citadel_auth`

**Files:**
- Create: `libs/citadel_auth/citadel_auth/catalog.py`
- Modify: `libs/citadel_auth/citadel_auth/__init__.py`
- Test: `libs/citadel_auth/tests/test_catalog.py`

**Interfaces:**
- Produces (later tasks use exactly these):
  - `DEFAULTS: dict[str, str]`
  - `class UnknownService(KeyError)`
  - `checked_address(value: object) -> str` (raises `ValueError`)
  - `advertised_url(host: str, port: int, configured: str | None = None) -> str` (env `CITADEL_ADVERTISE_URL` wins, then `configured`, then the host and port)
  - `resolved(value: str | Callable[[], str]) -> str`
  - `logical_url(name: str) -> str` returns `http://<name>.citadel`
  - `class CatalogTransport(httpx.AsyncBaseTransport)` with `__init__(catalog, inner=None)`
  - `class ServiceCatalog` with `__init__(keyring, treasury_url, *, cache_path=None, defaults=DEFAULTS, interval=30.0, transport=None)`, `url(name) -> str`, `mcp_url(name="armory") -> str`, `address(name) -> Callable[[], str]`, `async refresh() -> bool`, `async register(name, url, *, attempts=30, delay=2.0) -> bool`, `start(name=None, url=None) -> asyncio.Task`, `refresh_soon() -> None`, `async stop() -> None`

- [ ] **Step 1: Write the failing tests**

```python
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

    async def ensure_identity(self):
        return None


@pytest.fixture(autouse=True)
def _no_advertise_env(monkeypatch):
    monkeypatch.delenv("CITADEL_ADVERTISE_URL", raising=False)


def make(handler, tmp_path, **options):
    return ServiceCatalog(
        FakeKeyring(), "http://treasury.test:29602", cache_path=tmp_path / "catalog.json",
        transport=httpx.MockTransport(handler), **options,
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
```

- [ ] **Step 2: Run to verify they fail**

Run (in `libs/citadel_auth`): `uv run pytest tests/test_catalog.py -q -p no:cacheprovider`
Expected: FAIL, `ModuleNotFoundError: No module named 'citadel_auth.catalog'`.

- [ ] **Step 3: Implement `catalog.py`**

```python
"""Where the Citadel services are. Treasury keeps the catalog; each service registers its own address.

A service knows one address on its own: Treasury's (`treasury_url`). Everything else comes from here:
`url(name)` answers at request time from what the last refresh returned, else the disk cache of the last
good catalog, else the built-in defaults. A refresh that fails changes nothing, so a Treasury outage never
breaks calls between services that already know each other.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .client import service_client
from .keyring import Keyring

log = logging.getLogger(__name__)

DEFAULTS = {
    "treasury": "http://127.0.0.1:29602",
    "portcullis": "http://127.0.0.1:29601",
    "stronghold": "http://127.0.0.1:29650",
    "armory": "http://127.0.0.1:29600",
    "legion": "http://127.0.0.1:29603",
}
LOGICAL_SUFFIX = ".citadel"
_RETRY_STATUS = frozenset({502, 503, 504})


class UnknownService(KeyError):
    """The name is not a Citadel service in the catalog."""


def checked_address(value: object) -> str:
    """A base address `http(s)://host[:port]`, without the trailing slash. ValueError otherwise."""
    text = str(value or "").strip().rstrip("/") if isinstance(value, str) else ""
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment:
        raise ValueError("an address looks like http://host:port")
    return text


def advertised_url(host: str, port: int, configured: str | None = None) -> str:
    """The address other services use to reach this one: `CITADEL_ADVERTISE_URL`, else the configured one, else host and port."""
    chosen = os.getenv("CITADEL_ADVERTISE_URL") or configured
    if chosen:
        return checked_address(chosen)
    return f"http://{'127.0.0.1' if host in ('', '0.0.0.0', '::') else host}:{port}"


def resolved(value: str | Callable[[], str]) -> str:
    """A call site may hold a fixed address or a function that looks it up each time."""
    return value() if callable(value) else value


def logical_url(name: str) -> str:
    """A base URL for an httpx client; `CatalogTransport` swaps the host for the catalog address at send time."""
    return f"http://{name}{LOGICAL_SUFFIX}"


class ServiceCatalog:
    def __init__(
        self, keyring: Keyring, treasury_url: str, *, cache_path: Path | str | None = None,
        defaults: dict[str, str] = DEFAULTS, interval: float = 30.0, transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._keyring = keyring
        self._treasury_url = checked_address(treasury_url)
        self._cache_path = Path(cache_path) if cache_path else None
        self._known = dict(defaults)
        self._interval = interval
        self._transport = transport
        self._wake: asyncio.Event | None = None  # created in start(), inside the running loop
        self._task: asyncio.Task | None = None
        self._load_cache()

    def _load_cache(self) -> None:
        if self._cache_path is None:
            return
        try:
            stored = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self._merge(stored)

    def _merge(self, services: object) -> None:
        if not isinstance(services, dict):
            return
        for name, value in services.items():
            if name in self._known and name != "treasury":
                try:
                    self._known[name] = checked_address(value)
                except ValueError:
                    continue

    def url(self, name: str) -> str:
        if name == "treasury":
            return self._treasury_url
        try:
            return self._known[name]
        except KeyError:
            raise UnknownService(name) from None

    def mcp_url(self, name: str = "armory") -> str:
        return self.url(name) + "/mcp"

    def address(self, name: str) -> Callable[[], str]:
        return lambda: self.url(name)

    def _client(self) -> httpx.AsyncClient:
        options = {"transport": self._transport} if self._transport is not None else {}
        return service_client(self._keyring, "treasury", base_url=self._treasury_url, timeout=10.0, **options)

    async def refresh(self) -> bool:
        try:
            async with self._client() as client:
                response = await client.get("/services")
            if response.status_code != 200:
                return False
            services = response.json().get("services")
        except (httpx.HTTPError, ValueError, AttributeError):
            return False
        before = dict(self._known)
        self._merge(services)
        if self._known != before or (self._cache_path is not None and not self._cache_path.exists()):
            await asyncio.to_thread(self._write_cache)
        return True

    def _write_cache(self) -> None:
        if self._cache_path is None:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({k: v for k, v in self._known.items() if k != "treasury"}), encoding="utf-8")
            os.replace(temporary, self._cache_path)
        except OSError:
            log.warning("could not save the service catalog cache at %s", self._cache_path)

    async def register(self, name: str, url: str, *, attempts: int = 30, delay: float = 2.0) -> bool:
        """Tell Treasury where this service is. True once accepted. Retries while Treasury is down; a refusal is final."""
        body = {"url": checked_address(url)}
        for attempt in range(attempts):
            try:
                async with self._client() as client:
                    response = await client.put(f"/services/{name}", json=body)
                if response.status_code == 200:
                    return True
                if response.status_code not in _RETRY_STATUS:
                    log.error("Treasury refused the address of %r (%s): %s", name, response.status_code, response.text[:200])
                    return False
            except httpx.HTTPError:
                pass
            if attempt + 1 < attempts:
                await asyncio.sleep(delay)
        log.error("Treasury at %s did not accept the address of %r", self._treasury_url, name)
        return False

    def refresh_soon(self) -> None:
        """Ask the background loop to refresh now, e.g. after a call to a peer failed."""
        if self._wake is not None:
            self._wake.set()

    def start(self, name: str | None = None, url: str | None = None) -> asyncio.Task:
        """Register this service (when given) and keep refreshing. Call inside the running loop; `stop()` at shutdown."""
        self._wake = asyncio.Event()
        self._task = asyncio.create_task(self._run(name, url))
        return self._task

    async def _run(self, name: str | None, url: str | None) -> None:
        if name and url:
            await self.register(name, url)
        while True:
            await self.refresh()
            try:
                await asyncio.wait_for(self._wake.wait(), self._interval)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None


class CatalogTransport(httpx.AsyncBaseTransport):
    """Swaps `http://<name>.citadel` for the catalog address of `<name>` on every request; any other host passes through."""

    def __init__(self, catalog: ServiceCatalog, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._catalog = catalog
        self._inner = inner if inner is not None else httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host.endswith(LOGICAL_SUFFIX):
            target = httpx.URL(self._catalog.url(host[: -len(LOGICAL_SUFFIX)]))
            request.url = request.url.copy_with(scheme=target.scheme, host=target.host, port=target.port)
            request.headers["host"] = target.netloc.decode("ascii")
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()
```

- [ ] **Step 4: Export from the package**

In `libs/citadel_auth/citadel_auth/__init__.py` add the import line and extend `__all__`:

```python
from .catalog import (
    CatalogTransport, DEFAULTS as SERVICE_DEFAULTS, ServiceCatalog, UnknownService, advertised_url,
    checked_address, logical_url, resolved,
)
```

Add `"CatalogTransport", "SERVICE_DEFAULTS", "ServiceCatalog", "UnknownService", "advertised_url", "checked_address", "logical_url", "resolved"` to `__all__`.

- [ ] **Step 5: Run the library tests**

Run: `uv run pytest -q -p no:cacheprovider` in `libs/citadel_auth`
Expected: all pass (50 earlier plus the new ones).

- [ ] **Step 6: Sync the vendored copies and commit**

```bash
uv run scripts/sync_citadel_auth.py
uv run scripts/sync_citadel_auth.py --check
git add libs/citadel_auth apps/*/src/citadel_auth
git commit -m "feat(auth): add the service catalog client"
```

---

### Task 2: Treasury keeps the catalog

**Files:**
- Create: `apps/treasury/src/service_catalog.py`
- Modify: `apps/treasury/src/api.py` (routes next to `/instances`, admin routes next to `/admin/connections`)
- Test: `apps/treasury/tests/test_service_catalog.py`

**Interfaces:**
- Consumes: `citadel_auth.checked_address`, `settings_store.read_all/put/delete`, `current_caller()` (`.name`).
- Produces:
  - `service_catalog.REGISTERED_TABLE = "service_addresses"`, `PINNED_TABLE = "service_pins"`
  - `service_catalog.NAMES: frozenset[str]` (the four catalog services: `portcullis`, `stronghold`, `armory`, `legion`; Treasury is not in its own catalog)
  - `service_catalog.effective(db: Path) -> dict[str, str]` (pin, else registered)
  - `service_catalog.view(db: Path) -> dict` with `services: [{name, url, source, registered, pinned}]`, `source` is `pinned`, `registered` or `default`
  - `service_catalog.register(db, name, url) -> None`, `pin(db, name, url) -> None`, `unpin(db, name) -> None` (all raise `ServiceCatalogError`)
  - HTTP: `GET /services` -> `{"services": {name: url}}` (any known service); `PUT /services/{name}` body `{"url"}` (caller must be `name`); `GET /admin/services` -> `view`; `PUT /admin/services/{name}` body `{"url"}` pins; `DELETE /admin/services/{name}` unpins. Admin routes: Portcullis only, like `/admin/connections`.

- [ ] **Step 1: Write the failing tests**

```python
# apps/treasury/tests/test_service_catalog.py
import pytest

from src import service_catalog as catalog


@pytest.fixture
def db(tmp_path):
    return tmp_path / "settings.db"


def test_nothing_registered_means_an_empty_effective_catalog_and_defaults_in_the_view(db):
    assert catalog.effective(db) == {}
    names = {row["name"]: row for row in catalog.view(db)["services"]}
    assert set(names) == {"portcullis", "stronghold", "armory", "legion"}
    assert names["armory"]["source"] == "default" and names["armory"]["url"] == "http://127.0.0.1:29600"


def test_a_registration_is_kept_and_a_pin_beats_it(db):
    catalog.register(db, "armory", "http://armory:29600/")
    assert catalog.effective(db) == {"armory": "http://armory:29600"}
    catalog.pin(db, "armory", "http://armory.lan:29600")
    assert catalog.effective(db) == {"armory": "http://armory.lan:29600"}
    row = {r["name"]: r for r in catalog.view(db)["services"]}["armory"]
    assert (row["source"], row["registered"], row["pinned"]) == ("pinned", "http://armory:29600", "http://armory.lan:29600")
    catalog.unpin(db, "armory")
    assert catalog.effective(db) == {"armory": "http://armory:29600"}


@pytest.mark.parametrize("name", ["bard", "treasury", "", "Armory"])
def test_only_catalog_services_are_accepted(db, name):
    with pytest.raises(catalog.ServiceCatalogError):
        catalog.register(db, name, "http://x:1")


def test_a_bad_address_is_refused(db):
    with pytest.raises(catalog.ServiceCatalogError):
        catalog.register(db, "armory", "http://u:p@x:1")
    with pytest.raises(catalog.ServiceCatalogError):
        catalog.pin(db, "armory", "ftp://x")
```

Add HTTP tests in the same file, using the same app factory and caller-faking approach as `apps/treasury/tests/test_api.py` (open it and copy its client fixture; it already builds `create_app(manager, keyring, settings_db)` and signs as a named caller):

```python
def test_a_service_registers_only_itself(client_as, db_path):
    stronghold = client_as("stronghold")
    assert stronghold.put("/services/stronghold", json={"url": "http://stronghold:29650"}).status_code == 200
    assert stronghold.put("/services/armory", json={"url": "http://evil:1"}).status_code == 403
    assert client_as("armory").get("/services").json() == {"services": {"stronghold": "http://stronghold:29650"}}


def test_only_portcullis_pins_and_a_pin_shows_in_the_catalog(client_as):
    assert client_as("stronghold").put("/admin/services/armory", json={"url": "http://x:1"}).status_code == 403
    portcullis = client_as("portcullis")
    assert portcullis.put("/admin/services/armory", json={"url": "http://armory.lan:29600"}).status_code == 200
    assert client_as("legion").get("/services").json()["services"]["armory"] == "http://armory.lan:29600"
    assert portcullis.delete("/admin/services/armory").status_code == 200
    assert "armory" not in client_as("legion").get("/services").json()["services"]
```

(`client_as` and `db_path` are the existing fixtures' names in `test_api.py`; if they differ, create small equivalents in `conftest.py` that return a `TestClient` whose assertions are signed by the named service, exactly as `test_api.py` does for `portcullis`.)

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_service_catalog.py -q -p no:cacheprovider` in `apps/treasury`
Expected: FAIL, `cannot import name 'service_catalog'`.

- [ ] **Step 3: Implement the store**

```python
# apps/treasury/src/service_catalog.py
"""Where the Citadel services are. A service registers its own address; an administrator may pin one.

Two tables in `.data/treasury/settings.db`: `service_addresses` (what a service said about itself) and
`service_pins` (what an administrator set). A pin beats a registration, a registration beats the built-in default
(that default lives in `citadel_auth.catalog`, callers use it when this answers nothing).
"""

from __future__ import annotations

from pathlib import Path

from src.citadel_auth import SERVICE_DEFAULTS, checked_address, settings_store

REGISTERED_TABLE = "service_addresses"
PINNED_TABLE = "service_pins"
NAMES = frozenset({"portcullis", "stronghold", "armory", "legion"})


class ServiceCatalogError(ValueError):
    """A rejected change; the message is safe to show."""


def _checked(name: str, url: object) -> tuple[str, str]:
    if name not in NAMES:
        raise ServiceCatalogError(f"{name!r} is not a service in the catalog")
    try:
        return name, checked_address(url)
    except ValueError as error:
        raise ServiceCatalogError(str(error)) from error


def effective(db: Path) -> dict[str, str]:
    registered = settings_store.read_all(db, REGISTERED_TABLE)
    pinned = settings_store.read_all(db, PINNED_TABLE)
    return {name: str(pinned.get(name) or registered[name]) for name in sorted(NAMES) if pinned.get(name) or registered.get(name)}


def view(db: Path) -> dict:
    registered = settings_store.read_all(db, REGISTERED_TABLE)
    pinned = settings_store.read_all(db, PINNED_TABLE)
    rows = []
    for name in sorted(NAMES):
        source = "pinned" if pinned.get(name) else "registered" if registered.get(name) else "default"
        rows.append({
            "name": name,
            "url": str(pinned.get(name) or registered.get(name) or SERVICE_DEFAULTS[name]),
            "source": source,
            "registered": registered.get(name),
            "pinned": pinned.get(name),
        })
    return {"services": rows}


def register(db: Path, name: str, url: object) -> None:
    name, url = _checked(name, url)
    settings_store.put(db, REGISTERED_TABLE, name, url)


def pin(db: Path, name: str, url: object) -> None:
    name, url = _checked(name, url)
    settings_store.put(db, PINNED_TABLE, name, url)


def unpin(db: Path, name: str) -> None:
    if name not in NAMES:
        raise ServiceCatalogError(f"{name!r} is not a service in the catalog")
    settings_store.delete(db, PINNED_TABLE, name)
```

- [ ] **Step 4: Add the routes to `api.py`**

Import: `from src import service_catalog`. Next to `register_instance`:

```python
    class ServiceBody(BaseModel):
        url: str

    @app.get("/services")
    async def services() -> dict[str, Any]:
        """The catalog every service reads: the address each one registered, or an administrator pinned."""
        return {"services": service_catalog.effective(settings_db) if settings_db is not None else {}}

    @app.put("/services/{name}")
    async def register_service(name: str, body: ServiceBody) -> dict[str, Any]:
        """A service says where it is. Only a service may set its own address."""
        caller = current_caller()
        if caller is None or caller.name != name:
            raise HTTPException(403, f"{caller.name if caller else 'this caller'} may not register the address of {name!r}")
        if settings_db is None:
            raise HTTPException(409, "this Treasury keeps no settings database")
        try:
            service_catalog.register(settings_db, name, body.url)
        except service_catalog.ServiceCatalogError as error:
            raise HTTPException(400, str(error)) from error
        return {"saved": name}
```

After `/admin/default-cache`:

```python
    @app.get("/admin/services")
    async def admin_services() -> dict[str, Any]:
        _admin_only()
        return service_catalog.view(settings_db)

    @app.put("/admin/services/{name}")
    async def pin_service(name: str, body: ServiceBody) -> dict[str, Any]:
        _admin_only()
        try:
            service_catalog.pin(settings_db, name, body.url)
        except service_catalog.ServiceCatalogError as error:
            raise HTTPException(400, str(error)) from error
        return service_catalog.view(settings_db)

    @app.delete("/admin/services/{name}")
    async def unpin_service(name: str) -> dict[str, Any]:
        _admin_only()
        try:
            service_catalog.unpin(settings_db, name)
        except service_catalog.ServiceCatalogError as error:
            raise HTTPException(400, str(error)) from error
        return service_catalog.view(settings_db)
```

`ServiceBody` must be defined at module level (next to `InstanceBody`), not inside `create_app`; move it there.

- [ ] **Step 5: Run the Treasury tests**

Run: `uv run pytest -q -p no:cacheprovider` in `apps/treasury`
Expected: all pass (68 before). If `test_schema` or a table-name test flags the two new tables, add them to the allowed list that test reads (same fix as the `limits_and_prices` rename in Stronghold: table names must be known).

- [ ] **Step 6: Commit**

```bash
git add apps/treasury
git commit -m "feat(treasury): keep a catalog of service addresses"
```

---

### Task 3: Portcullis passes the catalog to the admin app

**Files:**
- Modify: `apps/portcullis/src/routes/admin_treasury.py` (same pattern as the connections routes added on 2026-11-18)
- Modify: `apps/portcullis/src/services/db_gateway.py` (`DbGatewayClient.admin` already exists; reuse it)
- Test: `apps/portcullis/tests/` (the file that tests the connections pass-through; find it with `grep -rl "treasury/connections" apps/portcullis/tests`)

**Interfaces:**
- Consumes: Treasury `GET/PUT/DELETE /admin/services...` from Task 2; Portcullis permission `settings.manage`, the one the connections routes use.
- Produces: `GET /api/admin/treasury/services`, `PUT /api/admin/treasury/services/{name}` body `{"url": str}`, `DELETE /api/admin/treasury/services/{name}`. Answers are Treasury's `view` JSON.

- [ ] **Step 1: Write the failing tests**

Copy the three tests that cover `/api/admin/treasury/connections` (list, put, delete, plus the 403 for an account without `settings.manage`) and change the paths to `/services` and the body to `{"url": "http://armory.lan:29600"}`. The fake Treasury those tests use needs the three new routes; extend it so `GET /admin/services` returns `{"services": []}`, and PUT/DELETE echo it.

- [ ] **Step 2: Run to verify they fail** (`uv run pytest tests/<that file> -q -p no:cacheprovider -k services`): expected 404.

- [ ] **Step 3: Implement**: in `admin_treasury.py`, add three routes that mirror the connections routes line for line (same dependency for the permission, same `DbGatewayRefused` to HTTP mapping, same audit-log call with action names `treasury.service_pin` and `treasury.service_unpin` and field names only, never values).

- [ ] **Step 4: Run** `uv run pytest -q -p no:cacheprovider tests/<that file>`: pass. The full suite runs in Task 9.

- [ ] **Step 5: Commit** `git commit -m "feat(portcullis): pass the service catalog to Treasury Admin"`

---

### Task 4: Treasury Admin "Services" page

**Files:**
- Create: `apps/treasury_admin/src/views/ServicesView.vue`, `apps/treasury_admin/src/views/__tests__/ServicesView.test.ts` (use the folder where `ConnectionsView`'s test lives)
- Modify: the page list in `apps/treasury_admin/src/router/pages.ts`, the API client file that holds the connections calls

**Interfaces:**
- Consumes: Task 3 routes.
- Produces: a page "Services" (permission `settings.manage`) with a table: name, address in use, source (`Pinned`, `Registered`, `Default`), a field to pin an address, and "Use the registered address" (unpin).

- [ ] **Step 1: Write the failing test** modelled on `ConnectionsView`'s: mount with a fake client returning `{services: [{name: "armory", url: "http://armory:29600", source: "registered", registered: "http://armory:29600", pinned: null}, ...]}`; assert one row per service with its source label; typing `http://armory.lan:29600` and pressing Pin calls `putService("armory", "http://armory.lan:29600")`; Unpin calls `deleteService("armory")`; a 400 error text is shown. Use `String(value)` for any v-model input.

- [ ] **Step 2: Run** `pnpm exec vitest run src/views/__tests__/ServicesView.test.ts`: expected FAIL (missing file).

- [ ] **Step 3: Implement** `ServicesView.vue` with the same layout classes and components as `ConnectionsView.vue` (read it first and reuse its card, table and error components; destructure client methods in the script so `vue-tsc` accepts them). Add `getServices`, `putService`, `deleteService` to the client next to the connection calls, and the page entry to `pages.ts`.

- [ ] **Step 4: Run** `pnpm exec vue-tsc -b` and `pnpm exec vitest run`: pass.

- [ ] **Step 5: Commit** `git commit -m "feat(treasury_admin): add the Services page"`

---

### Task 5: Bootstrap address and self-registration in every service

Each service gets `treasury_url` and an advertised address, builds one `ServiceCatalog` at start, and registers itself. Do the four services in order: Stronghold, Portcullis, Armory, Legion. Each is its own commit.

**Interfaces (all four):**
- Consumes: Task 1 (`ServiceCatalog`, `advertised_url`), Task 2 routes.
- Produces: in each app a module attribute `catalog: ServiceCatalog` built once; `settings.treasury_url: str`; start-up calls `catalog.start("<name>", advertised_url(host, port, settings.advertise_url))`; shutdown calls `await catalog.stop()`.
- Config: `configs/config_app.json` key `treasury_url` (default `http://127.0.0.1:29602`) and optional `advertise_url`; env `TREASURY_URL` wins over the file, env `CITADEL_ADVERTISE_URL` wins over `advertise_url`. No `DB_GATEWAY_URL`.

#### Task 5a: Stronghold

**Files:** `apps/stronghold/src/config.py` (replace `db_gateway_url` and its `DB_GATEWAY_URL` line by `treasury_url`, add `advertise_url`), `apps/stronghold/src/api.py` (lines near 85 to 110: lifespan), `apps/stronghold/configs/config_app.json` (add `"treasury_url"` is not written: leave the file with host and port; the default is the local address), tests in `apps/stronghold/tests/` that build `Settings(db_gateway_url=...)` or monkeypatch `DB_GATEWAY_URL` (find with `grep -rn "db_gateway_url\|DB_GATEWAY_URL" apps/stronghold/tests`).

- [ ] **Step 1: Failing test** in `apps/stronghold/tests/test_catalog_startup.py`:

```python
import httpx

from src.config import load_settings


def test_treasury_url_comes_from_the_environment_over_the_file(monkeypatch):
    monkeypatch.setenv("TREASURY_URL", "http://treasury:29602")
    assert load_settings().treasury_url == "http://treasury:29602"


def test_treasury_url_defaults_to_the_local_address(monkeypatch):
    monkeypatch.delenv("TREASURY_URL", raising=False)
    assert load_settings().treasury_url == "http://127.0.0.1:29602"
```

and a lifespan test that creates the app with a `FakeTreasury` transport (reuse the one in `tests/conftest.py`; extend it with `PUT /services/stronghold` and `GET /services`) and asserts the fake saw `PUT /services/stronghold` with the advertised URL.

- [ ] **Step 2: Run, see FAIL.** `uv run pytest tests/test_catalog_startup.py -q -p no:cacheprovider`
- [ ] **Step 3: Implement.** In `config.py`: field `treasury_url: str = "http://127.0.0.1:29602"` and `advertise_url: str | None = None`, loaded as `treasury_url=os.getenv("TREASURY_URL") or raw.get("treasury_url") or base.treasury_url`. In `api.py` lifespan, after `ensure_identity()`:

```python
catalog = ServiceCatalog(keyring, settings.treasury_url, cache_path=settings.data_dir / "catalog_cache.json")
app.state.catalog = catalog
catalog_task = catalog.start("stronghold", advertised_url(settings.host, settings.port, settings.advertise_url))
```

(skip the start when tests inject `store`, same condition as the existing `registration`), use `settings.treasury_url` where `settings.db_gateway_url` was used, and `await catalog.stop()` where `registration` is cancelled.
- [ ] **Step 4: Run** the whole Stronghold suite: `uv run pytest -q -p no:cacheprovider` (726 before): pass.
- [ ] **Step 5: Commit** `git commit -m "feat(stronghold): register with the service catalog"`

#### Task 5b: Portcullis

Same pattern. **Files:** `apps/portcullis/src/config.py` (`DbGatewaySettings`: drop `url`, keep `instance` and `connection`; add `treasury_url`, `advertise_url`; `db_gateway.url` in `configs/config_app.json` becomes `treasury_url`, and `docker/configs/portcullis/app.json` the same), `apps/portcullis/src/app.py` lines 141 to 147 (`httpx.AsyncClient(base_url=settings.db_gateway.url ...)`, `register_in_background(...)`), `apps/portcullis/src/services/config_validation.py` (line 98 checks `db_gateway.url`; check `treasury_url` instead, and drop the `mcp_server_url` row of the table at line 82 in Task 6), tests that build `DbGatewaySettings(url=...)`.

- [ ] Failing test: `load_settings().treasury_url` from `TREASURY_URL`; lifespan test with a fake Treasury sees `PUT /services/portcullis`.
- [ ] Implement as in 5a; the catalog cache path is `settings.database_path.parent / "catalog_cache.json"`; the catalog's name is `"portcullis"`.
- [ ] Run `uv run pytest -q -p no:cacheprovider -x -k "config or startup or db_gateway or lifespan"` for a fast check (full suite in Task 9).
- [ ] Commit `feat(portcullis): register with the service catalog`.

#### Task 5c: Armory

**Files:** `apps/armory/src/config.py` (`db_gateway_url` becomes `treasury_url`, read from `configs/config_app.json` key and env `TREASURY_URL`; add `advertise_url`), `apps/armory/src/environment_settings.py` (remove the `db_gateway_url` Spec at line 55 and `stronghold_url` at line 53 together with their group "Services Armory calls" when it is empty; delete the stored rows `db_gateway_url` and `stronghold_url` from the `environment` table on first read, using the same stale-row deletion the PDF and media limits used on 2026-11-18, find it with `grep -rn "stale" apps/armory/src`), `apps/armory/src/run.py` lines 36 to 40 (`register_in_background(...)` and start of the catalog; advertised name `"armory"`), `apps/armory/src/capabilities/notes/domain.py:45` (use `settings.treasury_url`), `apps/armory/docs/settings.md`, tests (`grep -rn "db_gateway_url\|stronghold_url" apps/armory/tests`).

- [ ] Failing tests: `settings.treasury_url` from env; the environment view no longer lists `db_gateway_url` or `stronghold_url`; a stored `stronghold_url` row is gone after the overlay runs.
- [ ] Implement; the catalog cache path is `data_dir(PROJECT_DIR) / "catalog_cache.json"`.
- [ ] Run `uv run pytest -q -p no:cacheprovider -m "not slow"` (1522 before): pass.
- [ ] Commit `feat(armory): register with the service catalog`.

#### Task 5d: Legion

**Files:** create `apps/legion/configs/config_app.json` (`{"treasury_url": "http://127.0.0.1:29602"}`) and extend `apps/legion/configs/README.md`; `apps/legion/src/runtime/gateway_settings.py` (`treasury_address()` now returns `TREASURY_URL` env, else the file, else `DEFAULT_TREASURY_URL`; delete `treasury_view`, `save_treasury_address`, `TREASURY_KEY`, the `ENVIRONMENT_TABLE` use for it); `apps/legion/src/server.py` (remove routes `/agents/treasury-address` at about lines 551 to 563; in `_register_with_treasury` also start the catalog, and when `SPEC.entry` is true register `"legion"` at the origin of `_AGENT_URL` (scheme and netloc, no `/mcp`)); `apps/portcullis/src/routes/agent_admin.py` and `apps/portcullis/src/services/agent_admin.py` (remove the two treasury-address routes and methods) with their tests; `apps/legion_admin/src/components/TreasuryAddressCard.vue`, its test, its use in the Connections view, and the client method; `apps/legion/tests/test_server_settings.py` (the two treasury-address tests become one test that the old route is gone); `apps/legion/README.md`.

- [ ] Failing tests: `treasury_address()` reads `TREASURY_URL` and the file; `PUT /agents/treasury-address` answers 404; an entry agent registers `legion` with the origin of its URL and a non-entry agent registers nothing.
- [ ] Implement. The catalog needs a keyring: `internal_auth.keyring`. The cache path is `data_dir(PROJECT_DIR) / "catalog_cache.json"`.
- [ ] Run `uv run pytest -q -p no:cacheprovider -m "not slow"` in Legion (1404 before), the Portcullis agent-admin tests, and in `legion_admin`: `pnpm exec vue-tsc -b` and `pnpm exec vitest run` (96 before, fewer by the removed card's tests).
- [ ] Commit `feat(legion): register with the service catalog; the Treasury address is a config value`.

---

### Task 6: Calls between services use the catalog

One commit per service. The rule: where a call site built a URL from `settings.<peer>_url`, it now asks the catalog at request time. Two mechanisms:

- **httpx clients with a `base_url`** (the `http(settings.x_url)` helper in Stronghold, `httpx.AsyncClient(base_url=...)` in Portcullis): build them with `base_url=logical_url("<name>")` and `transport=CatalogTransport(catalog, <existing transport or None>)`. Test code that injects its own transport keeps working because it replaces the inner transport.
- **Per-call URLs and MCP sessions** (`streamable_http_client(url, ...)`, `service_client(...).post(settings.x + path)`): replace the string with `catalog.url("<name>")` or `catalog.mcp_url()` evaluated at call time. Classes that store a URL at construction take `str | Callable[[], str]` and call `resolved(...)` when they use it; pass `catalog.address("armory")` (or `lambda: catalog.mcp_url()`).

**Interfaces:** Consumes Task 1 and Task 5. Produces: the config fields `stronghold_url`, `mcp_server_url` (Portcullis), `portcullis_url`, `armory_url` (Stronghold), `stronghold_url` (Armory) and their env variables (`STRONGHOLD_URL`, `PORTCULLIS_URL`, `ARMORY_URL`, `MCP_SERVER_URL` for Legion's `main`) no longer exist.

#### Task 6a: Stronghold

- `apps/stronghold/src/api.py`: `http(settings.db_gateway_url)` becomes `http_catalog("treasury")`, `PortcullisClient(http(settings.portcullis_url), keyring)` becomes `PortcullisClient(http_catalog("portcullis"), keyring)`, `armory or http(settings.armory_url)` becomes `armory or http_catalog("armory")`, with

```python
def http_catalog(name: str) -> httpx.AsyncClient:
    clients.append(httpx.AsyncClient(base_url=logical_url(name), timeout=_TIMEOUT, transport=CatalogTransport(catalog)))
    return clients[-1]
```

  (`logical_url("treasury")` resolves to the bootstrap address, since `ServiceCatalog.url("treasury")` returns `treasury_url`.) `register_in_background(keyring, settings.db_gateway_url, ...)` uses `settings.treasury_url`.
- `apps/stronghold/src/config.py`: delete `portcullis_url`, `armory_url` and their env lines. `apps/stronghold/README.md` table: remove the three rows, add `TREASURY_URL`.
- [ ] Failing test: build the app with a catalog whose `_known["armory"]` is `http://armory.test:29600` and a `MockTransport` inner; call a route that reaches Armory (memory list) and assert the request host is `armory.test`. Then change `_known["armory"]` and assert the next request goes to the new host without restarting.
- [ ] Implement, run `uv run pytest -q -p no:cacheprovider`, commit `refactor(stronghold): reach peers through the service catalog`.

#### Task 6b: Portcullis

- `apps/portcullis/src/app.py`: `StrongholdForwarder(upstream, settings.stronghold_url, ...)` becomes `StrongholdForwarder(upstream, logical_url("stronghold"), ...)` and the shared `upstream` client gets `transport=CatalogTransport(catalog, upstream_transport)`; `McpEmailSender(settings.mcp_server_url, ...)` and `McpServerTools(settings.mcp_server_url, ...)` take `catalog.address`-style callables: `lambda: catalog.mcp_url()`. Update both classes to call `resolved(self._url)` where they use the URL.
- `apps/portcullis/src/routes/mcp.py:161`, `routes/attachments.py:38`, `routes/capability_files.py:65`, `routes/server_info.py:65`: `settings.mcp_server_url` becomes `request.app.state.catalog.mcp_url()`.
- `apps/portcullis/src/config.py`: delete `stronghold_url`, `mcp_server_url`; `services/config_validation.py` row at line 82 removed; `configs/config_app.json` and `docker/configs/portcullis/app.json` lose the two keys; `configs/README.md` updated.
- [ ] Failing test: a Portcullis app with a fake catalog entry `armory` -> `http://armory.test:29600`; `GET /api/...` route that calls MCP (the existing server-info test) hits `armory.test`; changing the catalog changes the host on the next call.
- [ ] Implement, run the touched tests, commit `refactor(portcullis): reach peers through the service catalog`.

#### Task 6c: Armory

- `apps/armory/src/capabilities/obsidian/utils/brain_resolver.py:31`: `settings.stronghold_url.rstrip("/") + "/brains/resolve"` becomes `catalog.url("stronghold") + "/brains/resolve"`. Armory needs a module-level `catalog` that `run.py` starts: put it in `apps/armory/src/service_catalog.py` (`catalog = ServiceCatalog(keyring, settings.treasury_url, cache_path=...)`) and import it from both places.
- Remove `stronghold_url` from `config.py` (already removed from the Settings page in Task 5c).
- [ ] Failing test: `brain_resolver._resolve` posts to the catalog's Stronghold address (extend the existing test for it).
- [ ] Implement, run `uv run pytest -q -p no:cacheprovider -m "not slow"`, commit `refactor(armory): reach Stronghold through the service catalog`.

#### Task 6d: Legion

- `apps/legion/src/tools/mcp_client/mcp_upstream.py:78-82`: the `main` server's default URL. Today `MCP_SERVER_URL` overrides it. Replace the env lookup by `url_overrides = {_SERVER_ID: catalog.mcp_url()}` only when the stored `main` server has no URL of its own (read how `config.py` line 120 builds the default and keep a saved URL winning). Remove `--mcp-url` handling only if nothing else uses it (`apps/legion/src/server.py:33-39`: keep the flag, it is a CLI override).
- [ ] Failing test: with no saved `main` URL the upstream URL is `catalog.mcp_url()`; with a saved one it is that one.
- [ ] Implement, run `uv run pytest -q -p no:cacheprovider -m "not slow"`, commit `refactor(legion): the main MCP server defaults to the catalog address of Armory`.

---

### Task 7: Compose, docker configs and docs

**Files:** `docker-compose.yml`, `docker/configs/{portcullis,stronghold,treasury}/app.json`, `apps/*/.env.example` (only the lines about these URLs), `docs/deployment.md`, `apps/treasury/configs/README.md`, each service's `configs/README.md`, `apps/armory/docs/settings.md`, `apps/legion/README.md`.

- [ ] Compose: for armory, legion, stronghold and portcullis delete `DB_GATEWAY_URL`, `STRONGHOLD_URL`, `PORTCULLIS_URL`, `ARMORY_URL`, `MCP_SERVER_URL`; add to each `TREASURY_URL: http://treasury:29602` and `CITADEL_ADVERTISE_URL: http://<service>:<port>` (armory 29600, stronghold 29650, portcullis 29601, legion `http://legion:29603`). Keep `AI_AGENT_ADVERTISE_URL: http://legion` (Legion builds each agent's URL from it). Treasury needs neither.
- [ ] Remove `TREASURY_URL`-unrelated leftovers from `docker/configs/portcullis/app.json` (`mcp_server_url`, `stronghold_url`, `db_gateway.url`).
- [ ] Docs: in `docs/deployment.md` replace the sentence about service URLs set by Compose and the Legion exception I added on 2026-11-18 with: "Compose sets `TREASURY_URL` and `CITADEL_ADVERTISE_URL` for each service; every service registers its own address with Treasury at start, and finds the others in Treasury's catalog (Treasury Admin, Services)". Describe the catalog in `apps/treasury/configs/README.md` (tables, pins, precedence, the four names).
- [ ] Run `docker compose config` (the daemon is not needed) and confirm it prints no warnings about unset variables.
- [ ] Commit `docs: describe the service catalog; Compose sets TREASURY_URL and CITADEL_ADVERTISE_URL`.

---

### Task 8: Start-order and outage tests across the library

**Files:** Test: `libs/citadel_auth/tests/test_catalog_flow.py`

- [ ] Write a test that wires a real Treasury `create_app` (import is not possible from the library; use a minimal FastAPI stub that implements `PUT /services/{name}` and `GET /services` over a dict) behind `httpx.ASGITransport`, starts two `ServiceCatalog`s (`stronghold` and `armory`) **before** the stub accepts requests (the stub answers 503 for the first N calls), and asserts that after the stub is ready: both registered, each `url(other)` returns the other's registered address, and `CatalogTransport` routes a request for `http://armory.citadel` to it.
- [ ] Write a test that after both have refreshed, the stub starts answering 500: `url()` keeps the last addresses, and a restarted catalog (new object, same `cache_path`) starts with the cached addresses.
- [ ] Run `uv run pytest -q -p no:cacheprovider` in `libs/citadel_auth`; run `uv run scripts/sync_citadel_auth.py --check`.
- [ ] Commit `test(auth): start order and Treasury outage for the service catalog`.

---

### Task 9: Full verification, vault, close-out

- [ ] Run every suite and record the counts: `uv run pytest -q -p no:cacheprovider` in `apps/stronghold`, `apps/treasury`, `libs/citadel_auth`; `-m "not slow"` in `apps/armory` and `apps/legion`; Portcullis in the background (about 9 minutes); `pnpm exec vue-tsc -b` and `pnpm exec vitest run` in `legion_admin`, `treasury_admin`, `portcullis_admin`.
- [ ] `grep -rn "DB_GATEWAY_URL\|STRONGHOLD_URL\|PORTCULLIS_URL\|ARMORY_URL" --include=*.py --include=*.yml --include=*.md --include=*.example --include=*.json apps docker docker-compose.yml docs/deployment.md` finds nothing outside `docs/superpowers/` history and tests of removed behaviour.
- [ ] Add a short entry to `docs/deployment.md` troubleshooting: "A service reports 'connection refused' to a peer: open Treasury Admin, Services; pin the address if the peer registered a wrong one".
- [ ] Vault (in `D:\User\Documents\Programming\Brain`): add a line to `Projects/Citadel.md` Architecture and a Key decisions row (2026-11-18, "Service addresses live in Treasury's catalog; each service registers itself; `treasury_url` is the only bootstrap address", why: no circular start, no per-peer URL settings), update `Projects/treasury.md`, `treasury_admin.md`, `legion_admin.md` (Treasury card removed), `armory.md`, `stronghold.md`, `portcullis.md`, `garrison.md`, and the note `Decision - JSON configs are tracked and secrets live in .env.md`. Run `python Brain/_setup/hooks/validate_vault.py --all < /dev/null` from the Programming root: expect "vault OK".
- [ ] Commit the app repo (`git add -A`, message `Plan 13: service catalog in Treasury, done`) only when the user says to commit.

## Risks the executor must know

1. **Docker defaults are wrong until registration.** Before Stronghold has registered, `url("stronghold")` answers `http://127.0.0.1:29650`, which is not reachable inside a container. A call in that window fails like a peer that is down, and the background loop fixes it on the next refresh (30 s, or at once after `catalog.refresh_soon()`). Call `refresh_soon()` when a call to a peer raises a connection error, in the three request paths that matter (Portcullis to Stronghold, Stronghold to Portcullis, Armory to Stronghold).
2. **A pin can lock a wrong address in.** Pins win. The Services page shows the source of each address; the troubleshooting line in Task 9 says where to look.
3. **MCP sessions keep their URL for their lifetime.** Legion and Portcullis open MCP sessions per call, so they pick up a new address on the next call; a long-lived session (Legion's upstream pool, if it holds one) keeps the old address until reconnect. Check `apps/legion/src/tools/mcp_client/` when doing Task 6d and say so in the commit message if a pool needs a reset on catalog change.
4. **Not covered:** a live Docker run (daemon off on the dev machine), Treasury with real Postgres, a real browser check of the Services page, and a Windows restart of all services together. Say so in the final report.

## Self-review

- **Coverage:** circular start (Treasury holds the catalog, `treasury_url` is the one bootstrap value: Tasks 2, 5), registration and safety (own name only, address check, pin only through Portcullis: Task 2), outage (cache, defaults, retry: Task 1 and 8), admin control (Tasks 3, 4), every internal address in the table (Tasks 5, 6, 7), docs and vault (Tasks 7, 9).
- **Placeholders:** the per-site edits in Tasks 3, 5 and 6 name exact files and lines found by search on 2026-11-18, and tell the executor to read the surrounding class before editing; any line number may have moved by a few lines.
- **Names:** `ServiceCatalog`, `CatalogTransport`, `logical_url`, `advertised_url`, `checked_address`, `resolved`, `SERVICE_DEFAULTS`, `catalog.url/mcp_url/address/refresh/register/start/stop/refresh_soon`, `service_catalog.effective/view/register/pin/unpin`, tables `service_addresses` and `service_pins`, env `TREASURY_URL` and `CITADEL_ADVERTISE_URL` are used the same way in every task.

## Changes found during work

- Existing main worktree has uncommitted Legion, Compose and documentation edits. Implementation uses isolated `.worktrees/plan-13-service-catalog`, based on committed `main` (09cc60c7); original edits remain untouched.
- Task 1 FakeKeyring lacks `private_key` and `kid` required by real `sign_assertion`. Tests use in-memory Ed25519 identity; service authentication remains enabled.

- Verification blocker discovered in Task 3: existing Portcullis `tests/conftest.py::make_settings` writes temporary `.env`, and startup `ensure_secrets_key` writes an encryption key there. Existing shared auth test helpers also persist temporary signing identities. Automatic approval review refused Portcullis rerun under the no-`.env`/key-file rule; disposable-fixture exception requested before continuing. No tests weakened or bypassed.

- User approved existing disposable test-fixture `.env` and signing-key files only; real configuration and secret files remain prohibited.

- Task 4: existing navigation guard chooses first allowed page. Append Services after Instances/Connections to preserve default landing page; route must also be added to `router/index.ts`. Tests live beside views, not in `__tests__`.

- Task 5b: `test_db_gateway_client.py` asserted removed `DbGatewaySettings.url`; migrate its validation coverage to `treasury_url`, retaining instance checks.

- Task 5c: no stale environment-row deletion exists on committed main. Added narrow deletion for `db_gateway_url` and `stronghold_url` in `stored()`. Group retains Treasury instance/connection controls. Existing editable-URL tests now exercise Firecrawl address with unchanged assertions. Created shared Armory catalog module here for startup, reused in Task 6c.

- Task 5d: Legion previously registered in a daemon thread with no shutdown. Catalog and instance registration now share the serving event loop through the existing ASGI lifespan, preserving FastMCP lifecycle and cancelling both on shutdown.

- Task 6a: handle logical-peer connection errors in shared `CatalogTransport`, waking catalog refresh for both Stronghold→Portcullis and Portcullis→Stronghold without per-client callbacks. Added failing regression before implementation and resynced canonical library.

- Task 6b: test fixtures supplied removed `mcp_server_url`; seed the fake Armory address in the test catalog instead. Existing config validation tests now exercise Treasury bootstrap URL; environment pass-through tests use retained Firecrawl URL. Classes that store MCP URLs now accept callables and resolve each session.

- Task 6d: committed `load_servers_config` has no built-in `main` entry, and Legion retains persistent MCP sessions. Supply missing HTTP `main` only when catalog default is requested; saved URLs and stdio entries win, CLI override remains explicit. Keep catalog default as callable until session open so reconnect picks current address. Existing sessions retain their URL until reconnect. Failed startup catalog-backed sessions retry on next tools request; tested before implementation.

- Task 7: extra removed-address reference in `apps/armory/src/capabilities/obsidian/README.md`; update alongside service config docs. Compose validation uses `--no-env-resolution --quiet` and dummy gateway admin values, avoiding real `.env` reads and secret output; no Docker daemon required. Docker Compose file retains original LF endings.

- Task 8: FastAPI missing from library dev dependencies; added same minimum requirement as Treasury for planned ASGI stub. Tests exposed three defects in supplied Task 1 code: exhausted startup registration never retried again; removed pins stayed cached forever after successful snapshots; address checker accepted empty userinfo, invalid ports, whitespace, double-slash paths and empty query/fragment markers. Fixed after 11 observed regression failures. Background registration retries indefinitely for transient failures, stops on refusal, and refresh replaces valid snapshots while outages retain last good state. No security rule weakened.
