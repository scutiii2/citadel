# apps/treasury/src/service_catalog.py
"""Where the Citadel services are. A service registers its own address; an administrator may pin one.

Two tables in `.data/treasury/settings.db`: `service_addresses` (what a service said about itself) and
`service_pins` (what an administrator set). A pin beats a registration, a registration beats the built-in default
(that default lives in `citadel_auth.catalog`, callers use it when this answers nothing).
"""

from __future__ import annotations

from pathlib import Path

from src.citadel_auth import SERVICE_DEFAULTS, checked_address, settings_store

REGISTERED_TABLE = "service_addresses"
PINNED_TABLE = "service_pins"
NAMES = frozenset({"portcullis", "stronghold", "armory", "legion"})


class ServiceCatalogError(ValueError):
    """A rejected change; the message is safe to show."""


def _checked(name: str, url: object) -> tuple[str, str]:
    if name not in NAMES:
        raise ServiceCatalogError(f"{name!r} is not a service in the catalog")
    try:
        return name, checked_address(url)
    except ValueError as error:
        raise ServiceCatalogError(str(error)) from error


def effective(db: Path) -> dict[str, str]:
    registered = settings_store.read_all(db, REGISTERED_TABLE)
    pinned = settings_store.read_all(db, PINNED_TABLE)
    return {name: str(pinned.get(name) or registered[name]) for name in sorted(NAMES) if pinned.get(name) or registered.get(name)}


def view(db: Path) -> dict:
    registered = settings_store.read_all(db, REGISTERED_TABLE)
    pinned = settings_store.read_all(db, PINNED_TABLE)
    rows = []
    for name in sorted(NAMES):
        source = "pinned" if pinned.get(name) else "registered" if registered.get(name) else "default"
        rows.append({
            "name": name,
            "url": str(pinned.get(name) or registered.get(name) or SERVICE_DEFAULTS[name]),
            "source": source,
            "registered": registered.get(name),
            "pinned": pinned.get(name),
        })
    return {"services": rows}


def register(db: Path, name: str, url: object) -> None:
    name, url = _checked(name, url)
    settings_store.put(db, REGISTERED_TABLE, name, url)


def pin(db: Path, name: str, url: object) -> None:
    name, url = _checked(name, url)
    settings_store.put(db, PINNED_TABLE, name, url)


def unpin(db: Path, name: str) -> None:
    if name not in NAMES:
        raise ServiceCatalogError(f"{name!r} is not a service in the catalog")
    settings_store.delete(db, PINNED_TABLE, name)
