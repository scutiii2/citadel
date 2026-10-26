"""Base class for a capability: its identity, process-lifetime modules and always-on routes.
Each ``capabilities/<folder>/__init__.py`` subclasses it and exposes one instance as ``CAPABILITY``."""

from __future__ import annotations

from typing import ClassVar

from starlette.applications import Starlette

from src.services import capability_meta


class Capability:
    id: ClassVar[str]
    label: ClassVar[str]
    # Direct child packages kept across a reload (live engines, global library patches); editing them needs a restart.
    process_lifetime_modules: ClassVar[tuple[str, ...]] = ()

    def __init__(self) -> None:
        # The folder is the last part of the defining module's path, e.g. src.capabilities.notes -> notes.
        self.folder = type(self).__module__.rsplit(".", 1)[-1]
        self.meta = capability_meta.register(folder=self.folder, id=self.id, label=self.label)

    def install_routes(self, app: Starlette) -> None:
        """Mount this capability's always-on HTTP routes; they stay up while its tools are switched off."""

    def on_startup(self) -> None:
        """Run once when the server starts, only if the capability is loaded and enabled (e.g. resume background work)."""
