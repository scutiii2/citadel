"""Obsidian vault access through the Local REST API community plugin."""

from starlette.applications import Starlette

from src.services.capability_base import Capability


class Obsidian(Capability):
    id = "obsidian"
    label = "Obsidian"
    # Stores and runtimes here are shared with always-on routes; one identity per process.
    # Editing utils/ needs a restart; tool wrappers still reload.
    process_lifetime_modules = ("utils",)

    def install_routes(self, app: Starlette) -> None:
        from src.capabilities.obsidian.routes import install_brain_routes

        install_brain_routes(app)


CAPABILITY = Obsidian()
