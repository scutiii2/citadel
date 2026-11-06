"""Deterministic arithmetic and scoped equation solving."""

from src.services.capability_base import Capability


class Math(Capability):
    id = "math"
    label = "Mathematics"
    # Keep admission limits shared while wrappers are refreshed during a live call.
    process_lifetime_modules = ("utils",)

    def install_routes(self, app) -> None:
        """Attach worker cleanup to Armory's normal application lifespan."""
        from contextlib import asynccontextmanager

        from src.capabilities.math.utils.runner import runner

        previous = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(application):
            try:
                async with previous(application) as state:
                    yield state
            finally:
                await runner.close()

        app.router.lifespan_context = lifespan


CAPABILITY = Math()
