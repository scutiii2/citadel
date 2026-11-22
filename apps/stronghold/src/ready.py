"""Stronghold dependency health."""

from src.citadel_auth import ServiceCatalog
from src.citadel_auth.ready import Dependency


def dependencies(catalog: ServiceCatalog) -> list[Dependency]:
    return [Dependency(name, catalog.address(name)) for name in ("treasury", "legion", "armory", "portcullis")]
