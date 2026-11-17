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
        self._defaults = dict(defaults)
        self._known = dict(defaults)
        self._registration_refused = False
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
        if not isinstance(services, dict):
            return False
        before = dict(self._known)
        self._known = dict(self._defaults)
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
