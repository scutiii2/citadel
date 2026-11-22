"""Treasury reports process readiness independently of its database connections."""

from src.citadel_auth.ready import Probe


probe = Probe("treasury")


async def report() -> dict:
    return await probe.check([])
