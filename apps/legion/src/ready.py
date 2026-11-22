"""Legion probes Citadel services and its configured gateway addresses."""

import asyncio

from src.citadel_auth.ready import Dependency, PROBE_TIMEOUT, Probe
from src.runtime import gateway_settings
from src.runtime.service_catalog import catalog


probe = Probe("legion")


async def _gateway_address(which: str) -> str:
    try:
        async with asyncio.timeout(PROBE_TIMEOUT / 2):
            return (await gateway_settings.current(which)).url
    except TimeoutError:
        return gateway_settings.last_known(which).url


def dependencies() -> list[Dependency]:
    return [
        *(Dependency(name, catalog.address(name)) for name in ("treasury", "armory", "stronghold")),
        Dependency("conversation-gateway", lambda: _gateway_address(gateway_settings.KEY)),
        Dependency("decision-gateway", lambda: _gateway_address(gateway_settings.DECISION_KEY)),
    ]
