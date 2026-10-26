"""Single per-capability identity: a short id (chat "/<id>" alias and capability_registry/toggle name) and a label, declared once in each capability's ``__init__.py``.
Keyed by folder name, not short id; used by ``commands.py``, ``run.py`` and ``capability_routes.py``."""

from __future__ import annotations

from dataclasses import dataclass



@dataclass(frozen=True)
class CapabilityMeta:
    id: str
    label: str


_BY_FOLDER: dict[str, CapabilityMeta] = {}


def register(folder: str, id: str, label: str) -> CapabilityMeta:  # noqa: A002 - `id` reads best as-is here
    """Call once from ``capabilities/<folder>/__init__.py``; raises if `folder` was already registered (catches copy-paste mistakes)."""
    if folder in _BY_FOLDER:
        raise ValueError(f"Capability folder {folder!r} is already registered")
    meta = CapabilityMeta(id=id, label=label)
    _BY_FOLDER[folder] = meta
    return meta


def unregister(folder: str) -> None:
    """Forget `folder`'s id/label so its package can register again after a
    reload (see capability_loader.py). A folder that never registered is fine."""
    _BY_FOLDER.pop(folder, None)


def for_folder(folder: str) -> CapabilityMeta | None:
    """None for a folder that never called ``register()``; callers fall back to the folder name (see ``commands._infer_capability``)."""
    return _BY_FOLDER.get(folder)


def folder_for_id(id: str) -> str | None:  # noqa: A002 - matches register()'s `id` param name
    """Reverse of ``for_folder()``: the capability folder that registered this chat-facing id (e.g. ``"server"`` -> ``"server_manager"``), or None.
    Used by ``capability_help.py`` to find `help.json`."""
    for folder, meta in _BY_FOLDER.items():
        if meta.id == id:
            return folder
    return None
