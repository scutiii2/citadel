"""Finds capability folders and brings them online, offline, or back after an edit.
Going online imports fresh: old state removed, the folder's modules purged from ``sys.modules`` and its ``__pycache__`` deleted, then re-imported inside ``capability_registry.capturing()``. Modules in process_lifetime_modules need a restart. Runs on the event-loop thread under one lock; a failed import rolls back to offline and keeps the error text."""

from __future__ import annotations

import asyncio
import importlib
import logging
import pkgutil
import shutil
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.tools import tool_manager
from starlette.applications import Starlette

from src import commands
from src.services import capability_meta, capability_registry
from src.services.capability_base import Capability
from src.services.app_config import (
    capability_enabled,
    load_capabilities_config,
    migrate_capabilities_config,
    migrate_renamed_capabilities,
    save_capabilities_config,
)

logger = logging.getLogger(__name__)

# How much of a traceback is kept for the admin app to show.
TRACEBACK_LINES = 20
_DUPLICATE_PREFIX = "Tool already exists: "


class CapabilityError(Exception):
    """A capability request that cannot be done; ``status`` is the HTTP code."""

    status = 400


class UnknownCapability(CapabilityError):
    status = 404


class CapabilityLoadError(CapabilityError):
    status = 409


@dataclass
class CapabilityRecord:
    folder: str
    id: str
    label: str
    # True once tool.py was imported and captured (even while switched off).
    loaded: bool = False
    # The folder no longer exists on disk.
    missing: bool = False
    load_error: str | None = None
    capability: Capability | None = None


class _DuplicateToolWatcher(logging.Handler):
    """FastMCP does not raise for a second tool of the same name: it logs a
    warning and keeps the first. This catches that warning during an import."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.names: set[str] = set()

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if message.startswith(_DUPLICATE_PREFIX):
            self.names.add(message[len(_DUPLICATE_PREFIX):])


def _short_error(error: BaseException) -> str:
    lines = "".join(traceback.format_exception(error)).strip().splitlines()
    return "\n".join(lines[-TRACEBACK_LINES:])


class CapabilityLoader:
    def __init__(self, mcp: FastMCP, package: str, config_path: Path) -> None:
        self._mcp = mcp
        self._package = package
        self._config_path = config_path
        self._records: dict[str, CapabilityRecord] = {}  # by folder
        self._lock = asyncio.Lock()

    # --- reading -------------------------------------------------------------

    def records(self) -> list[CapabilityRecord]:
        return sorted(self._records.values(), key=lambda record: record.id)

    def record_for(self, name: str) -> CapabilityRecord | None:
        return next((record for record in self._records.values() if record.id == name), None)

    # --- discovery -----------------------------------------------------------

    def scan(self) -> None:
        """Find folders; read each new one's CAPABILITY without importing its tools."""
        importlib.invalidate_caches()
        package = importlib.import_module(self._package)
        found = {m.name for m in pkgutil.iter_modules(package.__path__) if m.ispkg and not m.name.startswith("_")}
        for folder in sorted(found - self._records.keys()):
            self._records[folder] = self._discover(folder)
        for folder, record in self._records.items():
            record.missing = folder not in found

    def _discover(self, folder: str) -> CapabilityRecord:
        try:
            capability = importlib.import_module(f"{self._package}.{folder}").CAPABILITY
            capability_registry.register_unloaded(capability.id, capability.label)
        except Exception as error:  # noqa: BLE001 - one bad folder must not stop the scan
            logger.warning("Capability folder %r cannot be read: %s", folder, error)
            return CapabilityRecord(folder, folder, folder, load_error=_short_error(error))
        return CapabilityRecord(folder, capability.id, capability.label, capability=capability)

    def startup(self) -> None:
        """Scan, migrate the config once, then load every folder with an entry.
        ``enabled: false`` is imported then switched off (tools stay listed); no entry stays unloaded."""
        self.scan()
        ids = [record.id for record in self._records.values() if record.load_error is None]
        migrate_renamed_capabilities(self._config_path)
        migrate_capabilities_config(self._config_path, ids)
        config = load_capabilities_config(self._config_path)
        for record in self._records.values():
            if record.load_error is not None or record.id not in config:
                continue
            try:
                self._load(record)
            except CapabilityLoadError as error:
                logger.warning("Capability %r did not load: %s", record.id, error)
                continue
            if not capability_enabled(config, record.id):
                capability_registry.set_enabled(self._mcp, record.id, False)

    def install_routes(self, app: Starlette) -> None:
        """Mount every readable capability's always-on routes, loaded or not; run once at startup."""
        for record in self.records():
            if record.capability is not None:
                record.capability.install_routes(app)

    async def refresh(self) -> None:
        async with self._lock:
            self.scan()

    # --- switching -----------------------------------------------------------

    async def set_online(self, name: str, online: bool) -> str:
        """Online: fresh import, then persist. Offline: persist, then hide the tools. Capabilities registered outside the scanner are only toggled.
        Returns the id it is registered under afterwards (going online can rename a record from folder name to its CAPABILITY id)."""
        async with self._lock:
            record = self.record_for(name)
            if record is None:
                if name not in capability_registry.names():
                    raise UnknownCapability(f"Unknown capability {name!r}")
                save_capabilities_config(self._config_path, name, online)
                capability_registry.set_enabled(self._mcp, name, online)
                return name
            if not online:
                save_capabilities_config(self._config_path, record.id, False)
                if record.loaded:
                    capability_registry.set_enabled(self._mcp, record.id, False)
                return record.id
            if record.missing:
                raise CapabilityLoadError(f"The folder of capability {name!r} no longer exists")
            self._load(record)
            try:
                save_capabilities_config(self._config_path, record.id, True)
            except Exception:
                capability_registry.set_enabled(self._mcp, record.id, False)
                raise
            return record.id

    # --- loading -------------------------------------------------------------

    def _load(self, record: CapabilityRecord) -> None:
        self._unload(record)
        self._purge(record.folder)
        tools_before = set(self._mcp._tool_manager._tools)
        templates_before = set(self._mcp._resource_manager._templates)
        watcher = _DuplicateToolWatcher()
        tool_manager.logger.addHandler(watcher)
        capability_id, label = record.id, record.label  # what this record owned before the attempt
        try:
            package = importlib.import_module(f"{self._package}.{record.folder}")
            # Reattach opt-in process-lifetime children to the fresh parent package.
            # These may own global library patches or a live background engine.
            for child in package.CAPABILITY.process_lifetime_modules:
                module = sys.modules.get(f"{package.__name__}.{child}")
                if module is not None:
                    setattr(package, child, module)
            capability = package.CAPABILITY
            other = next((r for r in self._records.values() if r.folder != record.folder and r.id == capability.id), None)
            if other is not None:
                capability_meta.unregister(record.folder)
                raise CapabilityLoadError(f"Capability id {capability.id!r} is already used by folder {other.folder!r}")
            capability_id, label = capability.id, capability.label
            with capability_registry.capturing(self._mcp, capability.id, label=capability.label):
                importlib.import_module(f"{self._package}.{record.folder}.tool")
            if watcher.names:
                raise CapabilityLoadError(
                    f"Tool name already used by another capability: {', '.join(sorted(watcher.names))}"
                )
        except Exception as error:
            self._roll_back(capability_id, label, tools_before, templates_before)
            record.id, record.label, record.loaded = capability_id, label, False
            record.load_error = str(error) if isinstance(error, CapabilityLoadError) else _short_error(error)
            if isinstance(error, CapabilityLoadError):
                raise
            raise CapabilityLoadError(record.load_error) from error
        finally:
            tool_manager.logger.removeHandler(watcher)
        record.id, record.label, record.loaded, record.load_error = capability.id, capability.label, True, None
        record.capability = capability

    def _unload(self, record: CapabilityRecord) -> None:
        capability_registry.discard(self._mcp, record.id)
        commands.remove_capability(record.id)
        capability_meta.unregister(record.folder)
        record.loaded = False

    def _purge(self, folder: str) -> None:
        prefix = f"{self._package}.{folder}"
        package = sys.modules.get(prefix)
        # Only a direct child can be retained; all capabilities default to a full purge.
        modules = getattr(getattr(package, "CAPABILITY", None), "process_lifetime_modules", ())
        retained = tuple(f"{prefix}.{child}" for child in modules
                         if isinstance(child, str) and child.isidentifier())
        for name in [name for name in sys.modules if name == prefix or name.startswith(prefix + ".")]:
            if not any(name == child or name.startswith(child + ".") for child in retained):
                del sys.modules[name]
        # Stale bytecode: same mtime (whole seconds) and size would be trusted.
        package_dir = Path(importlib.import_module(self._package).__path__[0]) / folder
        for cache in package_dir.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)
        importlib.invalidate_caches()

    def _roll_back(self, capability_id: str, label: str, tools_before: set[str], templates_before: set[str]) -> None:
        """Undo a failed import: whatever it half-registered goes, and the
        capability stays listed as an offline handle with no tools."""
        capability_registry.discard(self._mcp, capability_id)
        for name in set(self._mcp._tool_manager._tools) - tools_before:
            self._mcp.remove_tool(name)
        for uri in set(self._mcp._resource_manager._templates) - templates_before:
            self._mcp._resource_manager._templates.pop(uri, None)
        commands.remove_capability(capability_id)
        capability_registry.register_unloaded(capability_id, label)
