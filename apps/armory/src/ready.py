"""Armory dependency health."""

from src.citadel_auth.ready import Dependency, Probe
from src.service_catalog import catalog


probe = Probe("armory")


def dependencies() -> list[Dependency]:
    return [Dependency("treasury", catalog.address("treasury"))]
