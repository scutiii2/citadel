"""Legion probes the Citadel services it calls. The model gateways run inside Legion."""

from src.citadel_auth.ready import Dependency, Probe
from src.runtime.service_catalog import catalog


probe = Probe("legion")


def dependencies() -> list[Dependency]:
    return [Dependency(name, catalog.address(name)) for name in ("treasury", "armory", "stronghold")]
