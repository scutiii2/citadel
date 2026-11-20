"""The Bard, Scribe and Reader connections Stronghold holds: Treasury origin ids, a parent token and per-origin overrides."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.citadel_auth import settings_store

REQUIRED = {"bard": "Bard", "scribe": "Scribe", "reader": "Reader"}
TABLE = "tool_services"


def _empty() -> dict:
    return {"enabled": True, "service_id": None, "origins": [], "token": ""}


class ToolStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def get(self, name: str) -> dict:
        return {**_empty(), **settings_store.read_all(self._path, TABLE).get(name, {})}

    def records(self) -> dict[str, dict]:
        saved = settings_store.read_all(self._path, TABLE)
        return {name: {**_empty(), **saved.get(name, {})} for name in REQUIRED}

    def put(self, name: str, record: dict) -> None:
        settings_store.put(self._path, TABLE, name, record)

    def clear(self, name: str) -> None:
        settings_store.delete(self._path, TABLE, name)


def token_for(record: dict, origin: dict) -> str:
    """The origin's own token, else the connection's."""
    return origin.get("header_value") or record["token"]


def ready_status(name: str, record: dict) -> dict:
    label = REQUIRED[name]
    if not record["enabled"]:
        return {"ready": False, "reason": f"{label} is disabled in Stronghold Admin."}
    if not record["origins"]:
        return {"ready": False, "reason": f"Configure {label} in Stronghold Admin."}
    if not all(token_for(record, origin) for origin in record["origins"]):
        return {"ready": False, "reason": f"Set the {label} token in Stronghold Admin."}
    return {"ready": True, "reason": None}


def view(name: str, record: dict, resolve: Callable[[str], str | None]) -> dict:
    """What the admin page may see: no token, only whether one is set."""
    return {
        "name": name, "label": REQUIRED[name], "enabled": record["enabled"], "service_id": record["service_id"],
        "has_token": bool(record["token"]),
        "origins": [{"origin_id": o["origin_id"], "origin": resolve(o["origin_id"]), "has_override": bool(o.get("header_value"))}
                    for o in record["origins"]],
        **ready_status(name, record),
    }
