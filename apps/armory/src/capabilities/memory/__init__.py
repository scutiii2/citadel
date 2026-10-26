"""Per-user notes that outlive a chat."""

from starlette.applications import Starlette

from src.services.capability_base import Capability


class Memory(Capability):
    id = "memory"
    label = "Memory"

    def install_routes(self, app: Starlette) -> None:
        from src.capabilities.memory.routes import install_memory_routes

        install_memory_routes(app)


CAPABILITY = Memory()
