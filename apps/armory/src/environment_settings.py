"""Deployment values an administrator changes while Armory runs, kept in `.data/armory/settings.db` (table `environment`).

The `.env` file and the built-in defaults still give the starting value; a stored value wins over both. Removing a
stored value puts the `.env` or default value back. A secret (signing key, API key) is write-only: the view says
whether one is set and never returns it. Part of a value is read once when a capability starts (the semantic index,
the link signing key and the Treasury registration), so a change to those is saved at once and used from the next start.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.citadel_auth import settings_store

logger = logging.getLogger(__name__)

TABLE = "environment"


@dataclass(frozen=True)
class Spec:
    field: str
    label: str
    group: str
    kind: str  # "text" | "url" | "number" | "bool" | "path"
    help: str = ""
    secret: bool = False
    restart: bool = False  # read once at startup or when a capability first starts


SPECS: tuple[Spec, ...] = (
    Spec("pdf_merger_public_base_url", "Public address of PDF links", "PDF and video links", "url",
         "Blank: http://127.0.0.1 and Armory's port."),
    Spec("pdf_merger_signing_key", "PDF link signing key", "PDF and video links", "text",
         "Signs the links. Blank: PDF links stop working after a restart.", secret=True, restart=True),
    Spec("media_public_base_url", "Public address of video links", "PDF and video links", "url",
         "Blank: http://127.0.0.1 and Armory's port."),
    Spec("media_signing_key", "Video link signing key", "PDF and video links", "text",
         "Signs the links. Blank: video links stop working after a restart.", secret=True, restart=True),
    Spec("tavily_api_key", "Tavily API key", "Web research and scraping", "text",
         "Tried first by the web tools. Get one at app.tavily.com.", secret=True),
    Spec("firecrawl_api_key", "Firecrawl API key", "Web research and scraping", "text",
         "The hosted Firecrawl service, tried second. Get one at firecrawl.dev.", secret=True),
    Spec("firecrawl_local_url", "Firecrawl Local address", "Web research and scraping", "url",
         "Your own Firecrawl Local server, tried third. Blank: not used."),
    Spec("firecrawl_local_token", "Firecrawl Local token", "Web research and scraping", "text",
         "The token that server asks for.", secret=True),
    Spec("db_gateway_instance", "Treasury instance name", "Services Armory calls", "text",
         "The name Armory registers itself under in Treasury.", restart=True),
    Spec("db_gateway_connection", "Treasury connection", "Services Armory calls", "text",
         "The connection the notes use.", restart=True),
    Spec("workspace_dir", "Workspace folder (read-only tools)", "Folders the read-only tools look at", "path",
         "Relative to apps/armory/ unless absolute."),
)
BY_FIELD = {spec.field: spec for spec in SPECS}


class SettingError(ValueError):
    """A value is refused; the message names the setting and is safe to show."""


def coerce(spec: Spec, raw: Any) -> Any:
    """The value as the Settings field holds it. Raises SettingError."""
    if spec.kind == "bool":
        if isinstance(raw, bool):
            return raw
        raise SettingError(f"{spec.label}: use on or off.")
    if spec.kind == "number":
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
            raise SettingError(f"{spec.label}: use a number above 0.")
        return float(raw)
    if not isinstance(raw, str) or not raw.strip():
        raise SettingError(f"{spec.label}: enter a value, or reset it.")
    text = raw.strip()
    if spec.kind == "url":
        parts = urlsplit(text)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            raise SettingError(f"{spec.label}: use an http(s) address without a login.")
    return Path(text) if spec.kind == "path" and spec.field.endswith("_dir") else text


def stored(path: Path) -> dict[str, Any]:
    values = settings_store.read_all(path, TABLE)
    for name in ("db_gateway_url", "stronghold_url"):
        if name in values:
            settings_store.delete(path, TABLE, name)
            del values[name]
    return values


def overlay(base: Any, path: Path) -> Any:
    """`base` (a Settings) with every stored value applied. A stored value that no longer validates is skipped."""
    values: dict[str, Any] = {}
    for field, raw in stored(path).items():
        spec = BY_FIELD.get(field)
        if spec is None:
            continue
        try:
            values[field] = coerce(spec, raw)
        except SettingError as error:
            logger.warning("Stored setting ignored: %s", error)
    return dataclasses.replace(base, **values) if values else base


def _shown(spec: Spec, value: Any) -> Any:
    return str(value) if isinstance(value, Path) else value


def view(current: Any, path: Path) -> dict[str, Any]:
    """Every setting with its effective value and where it comes from. A secret shows only `has_value`."""
    saved = stored(path)
    rows = []
    for spec in SPECS:
        value = getattr(current, spec.field)
        row: dict[str, Any] = {
            "field": spec.field, "label": spec.label, "group": spec.group, "kind": spec.kind, "help": spec.help,
            "secret": spec.secret, "restart": spec.restart, "stored": spec.field in saved,
        }
        if spec.secret:
            row["has_value"] = bool(value)
        else:
            row["value"] = _shown(spec, value)
        rows.append(row)
    return {"settings": rows}


def update(current: Any, defaults: Any, path: Path, changes: dict[str, Any]) -> list[str]:
    """Save `changes` (field -> value, or None to go back to the `.env`/default value) and use them now.

    Nothing is saved if one change is refused. Returns the changed fields that are used only after a restart."""
    if not isinstance(changes, dict) or not changes:
        raise SettingError("Send at least one setting to change.")
    checked: dict[str, Any] = {}
    for field, raw in changes.items():
        spec = BY_FIELD.get(field)
        if spec is None:
            raise SettingError(f"Unknown setting: {field}.")
        checked[field] = None if raw is None else coerce(spec, raw)
    for field, value in checked.items():
        if value is None:
            settings_store.delete(path, TABLE, field)
            value = getattr(defaults, field)
        else:
            raw = changes[field]
            settings_store.put(path, TABLE, field, raw.strip() if isinstance(raw, str) else raw)
        object.__setattr__(current, field, value)  # Settings is frozen; every module shares this one object.
    return [field for field in checked if BY_FIELD[field].restart]
