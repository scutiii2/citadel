"""Support tickets: report bugs and failures, suggest features, follow your own tickets."""

from starlette.applications import Starlette

from src.services.capability_base import Capability


class Tickets(Capability):
    id = "ticket"
    label = "Tickets"
    # Stores and runtimes here are shared with always-on routes; one identity per process.
    # Editing utils/ needs a restart; tool wrappers still reload.
    process_lifetime_modules = ("utils",)

    def install_routes(self, app: Starlette) -> None:
        from src.capabilities.tickets.routes import install_ticket_routes

        install_ticket_routes(app)


CAPABILITY = Tickets()
