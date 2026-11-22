"""Discover known Compose services through their public health endpoints."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from src import outside_catalog, service_catalog


KNOWN = {
    "portcullis": "http://portcullis:29601",
    "stronghold": "http://stronghold:29650",
    "legion": "http://legion:29603",
    "armory": "http://armory:29600",
    "conversation-gateway": "http://conversation-gateway:29407",
    "decision-gateway": "http://decision-gateway:29406",
}
_LOG = logging.getLogger(__name__)
_TIMEOUT = 2.0
_last_result: dict[str, list[str]] = {"found": [], "registered": [], "missed": []}


def last_result() -> dict[str, list[str]]:
    return {key: list(names) for key, names in _last_result.items()}


def _known_entries(db: Path) -> set[str]:
    existing = set(service_catalog.effective(db))
    for group in outside_catalog.view(db)["groups"]:
        origins = {item["origin"] for item in group["origins"]}
        for name, url in KNOWN.items():
            if name not in service_catalog.NAMES and ((group["name"] == name and origins) or url in origins):
                existing.add(name)
    return existing


async def _reachable(client: httpx.AsyncClient, address: str) -> bool:
    try:
        async with asyncio.timeout(_TIMEOUT):
            async with client.stream("GET", address + "/health", timeout=_TIMEOUT, follow_redirects=False) as response:
                return response.is_success
    except (httpx.HTTPError, TimeoutError):
        return False


async def discover(db: Path, client: httpx.AsyncClient) -> dict[str, list[str]]:
    """Probe missing entries concurrently, inserting only while their catalog slot is empty."""
    global _last_result
    existing = await asyncio.to_thread(_known_entries, db)
    candidates = {name: address for name, address in KNOWN.items() if name not in existing}
    reachable = await asyncio.gather(*(_reachable(client, address) for address in candidates.values()))
    found, registered, missed = [], [], []
    for (name, address), is_up in zip(candidates.items(), reachable, strict=True):
        if not is_up:
            missed.append(name)
            continue
        found.append(name)
        insert = service_catalog.register_if_missing if name in service_catalog.NAMES else outside_catalog.discover_origin
        if await asyncio.to_thread(insert, db, name, address):
            registered.append(name)
    _last_result = {"found": found, "registered": registered, "missed": missed}
    return last_result()


async def run(db: Path) -> None:
    """Keep discovery independent from startup and retry a failed round."""
    async with httpx.AsyncClient(trust_env=False) as client:
        while True:
            try:
                await discover(db, client)
            except Exception as error:
                _LOG.warning("Treasury discovery round failed (%s)", type(error).__name__)
            await asyncio.sleep(60)
