"""A service tells Treasury which connections its own instance may use.

Treasury keeps no list of its callers. Each service registers its own instance at start, so adding
a service never means editing Treasury. Treasury only accepts an instance the caller owns (its own
name, or the one name it is known by) and only connections Treasury has configured.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from urllib.parse import quote

import httpx

from .client import service_client
from .keyring import Keyring

log = logging.getLogger(__name__)

# What is retried: Treasury not up yet, or briefly failing. A 4xx is a wrong setting and is not retried.
_RETRY_STATUS = frozenset({502, 503, 504})


async def register_instance(
    keyring: Keyring, treasury_url: str, instance: str, connections: Iterable[str],
    *, attempts: int = 30, delay: float = 2.0,
) -> bool:
    """Register `instance` with the connections it needs. True once Treasury accepted it."""
    path = f"/instances/{quote(instance, safe='')}"
    body = {"connections": list(dict.fromkeys(connections))}
    for attempt in range(attempts):
        try:
            async with service_client(keyring, "treasury", base_url=treasury_url.rstrip("/"), timeout=10.0) as client:
                response = await client.put(path, json=body)
            if response.status_code == 200:
                return True
            if response.status_code not in _RETRY_STATUS:
                log.error("Treasury refused instance %r (%s): %s", instance, response.status_code, response.text[:200])
                return False
        except httpx.HTTPError:
            pass
        if attempt + 1 < attempts:
            await asyncio.sleep(delay)
    log.error("Treasury at %s did not accept instance %r; it stays unregistered", treasury_url, instance)
    return False


def register_in_background(
    keyring: Keyring, treasury_url: str, instance: str, connections: Iterable[str], **options: float,
) -> asyncio.Task[bool]:
    """Start `register_instance` without waiting for it. Keep the task and cancel it at shutdown."""
    return asyncio.create_task(register_instance(keyring, treasury_url, instance, list(connections), **options))
