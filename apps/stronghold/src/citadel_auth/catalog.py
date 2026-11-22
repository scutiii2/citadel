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
    text = value.strip() if isinstance(value, str) else ""
    try:
        parts = urlsplit(text)
        port = parts.port  # Reject malformed and out-of-range ports before saving.
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.path not in ("", "/") or "?" in text or "#" in text
                or parts.netloc.endswith(":") or port == 0 or "\\" in text
                or any(char.isspace() or ord(char) < 32 for char in text)):
            raise ValueError
        httpx.URL(text)
    except (ValueError, httpx.InvalidURL):
        raise ValueError("an address looks like http://host:port") from None
    return text.removesuffix("/")


def advertised_url(host: str, port: int, configured: str | None = None) -> str:
    """The address other services use to reach this one: `CITADEL_ADVERTISE_URL`, else the configured one, else host and port."""
    chosen = os.getenv("CITADEL_ADVERTISE_URL") or configured
    if chosen:
        return checked_address(chosen)
    listener = "127.0.0.1" if host in ("", "0.0.0.0", "::") else host
    if ":" in listener and not listener.startswith("["):
        listener = f"[{listener}]"
    return checked_address(f"http://{listener}:{port}")


def resolved(value: str | Callable[[], str]) -> str:
    """A call site may hold a fixed address or a function that looks it up each time."""
    return value() if callable(value) else value


def logical_url(name: str) -> str:
    """A base URL for an httpx client; `CatalogTransport` swaps the host for the catalog address at send time."""
    return f"http://{name}{LOGICAL_SUFFIX}"


def _clean_outside(groups: object) -> list[dict]:
    """Keep well-formed groups and addresses from Treasury or the local cache."""
    if not isinstance(groups, list):
        return []
    cleaned = []
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("service_id"), str) or not isinstance(group.get("name"), str):
            continue
        origins = []
        items = group.get("origins")
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("origin_id"), str):
                continue
            try:
                origin = checked_address(item.get("origin"))
            except ValueError:
                continue
            origins.append({"origin_id": item["origin_id"], "origin": origin})
        cleaned.append({"service_id": group["service_id"], "name": group["name"], "origins": origins})
    return cleaned


class ServiceCatalog:
    def __init__(
        self, keyring: Keyring, treasury_url: str, *, cache_path: Path | str | None = None,
        defaults: dict[str, str] = DEFAULTS, interval: float = 30.0, transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._keyring = keyring
        self._treasury_url = checked_address(treasury_url)
        self._cache_path = Path(cache_path) if cache_path else None
        self._defaults = dict(defaults)
        self._known = dict(defaults)
        self._registration_refused = False
        self._interval = interval
        self._transport = transport
        self._wake: asyncio.Event | None = None  # created in start(), inside the running loop
        self._task: asyncio.Task | None = None
        self._refresh_lock = asyncio.Lock()
        self._outside: list[dict] = []
        self._load_cache()

    def _load_cache(self) -> None:
        if self._cache_path is None:
            return
        try:
            stored = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self._merge(self._known, stored)
        if isinstance(stored, dict):
            self._outside = _clean_outside(stored.get("_outside"))

    @staticmethod
    def _merge(known: dict[str, str], services: object) -> None:
        if not isinstance(services, dict):
            return
        for name, value in services.items():
            if name in known and name != "treasury":
                try:
                    known[name] = checked_address(value)
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

    def outside_groups(self) -> list[dict]:
        return [{**group, "origins": [dict(o) for o in group["origins"]]} for group in self._outside]

    def outside_group(self, service_id: str) -> dict:
        for group in self._outside:
            if group["service_id"] == service_id:
                return {**group, "origins": [dict(origin) for origin in group["origins"]]}
        raise UnknownService(service_id)

    def outside_origin(self, origin_id: str) -> str:
        for group in self._outside:
            for item in group["origins"]:
                if item["origin_id"] == origin_id:
                    return item["origin"]
        raise UnknownService(origin_id)

    async def _read_outside(self, client: httpx.AsyncClient) -> list[dict] | None:
        """Keep the last snapshot when Treasury cannot serve the outside catalog."""
        try:
            response = await client.get("/outside")
            groups = response.json().get("groups") if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError, AttributeError):
            return None
        return _clean_outside(groups) if isinstance(groups, list) else None

    def address(self, name: str) -> Callable[[], str]:
        return lambda: self.url(name)

    def _client(self) -> httpx.AsyncClient:
        options = {"transport": self._transport} if self._transport is not None else {}
        return service_client(self._keyring, "treasury", base_url=self._treasury_url, timeout=10.0, **options)

    async def refresh(self) -> bool:
        try:
            async with self._refresh_lock, self._client() as client:
                response = await client.get("/services")
                services = response.json().get("services") if response.status_code == 200 else None
                services_ok = isinstance(services, dict)
                if services_ok:
                    known = dict(self._defaults)
                    self._merge(known, services)
                    if known != self._known or (self._cache_path is not None and not self._cache_path.exists()):
                        await asyncio.to_thread(self._write_cache, known, self._outside)
                    self._known = known

                outside = await self._read_outside(client)
                if outside is not None and outside != self._outside:
                    await asyncio.to_thread(self._write_cache, self._known, outside)
                    self._outside = outside
        except (httpx.HTTPError, ValueError, AttributeError):
            return False
        return services_ok

    def _write_cache(self, known: dict[str, str], outside: list[dict]) -> None:
        if self._cache_path is None:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._cache_path.with_suffix(".tmp")
            stored = {key: value for key, value in known.items() if key != "treasury"}
            stored["_outside"] = outside
            temporary.write_text(json.dumps(stored), encoding="utf-8")
            os.replace(temporary, self._cache_path)
        except OSError:
            log.warning("could not save the service catalog cache at %s", self._cache_path)

    async def register(self, name: str, url: str, *, attempts: int = 30, delay: float = 2.0) -> bool:
        """Tell Treasury where this service is. True once accepted. Retries while Treasury is down; a refusal is final."""
        self._registration_refused = False
        body = {"url": checked_address(url)}
        for attempt in range(attempts):
            try:
                async with self._client() as client:
                    response = await client.put(f"/services/{name}", json=body)
                if response.status_code == 200:
                    return True
                if response.status_code not in _RETRY_STATUS:
                    self._registration_refused = True
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
        pending = bool(name and url)
        while True:
            if pending:
                accepted = await self.register(name, url, attempts=1)
                pending = not accepted and not self._registration_refused
            await self.refresh()
            try:
                await asyncio.wait_for(self._wake.wait(), min(self._interval, 2.0) if pending else self._interval)
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
        try:
            return await self._inner.handle_async_request(request)
        except httpx.ConnectError:
            if host.endswith(LOGICAL_SUFFIX):
                self._catalog.refresh_soon()
            raise

    async def aclose(self) -> None:
        await self._inner.aclose()
