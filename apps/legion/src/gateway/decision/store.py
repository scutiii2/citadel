"""Gateways, saved in gateways.json in the state folder. Secrets are write-only: they are read for calls and never
returned. shortcut: secrets are stored in clear text because they must be sent as they are; the file is private to
the data folder. Upgrade to a secret store if the host is shared."""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

import sqlite3

from src.citadel_auth import settings_store
from src.gateway.shared import MAX_TOKEN, valid_url as _valid_url

KINDS = ("typesafe", "ollama", "scuti", "freellmapi")
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_TIMEOUT = 60
_SECRETS = {"api_key": "has_api_key", "token": "has_token"}
ENV_REF = re.compile(r"env:([A-Z][A-Z0-9_]{0,63})")
_FIELDS = {
    "typesafe": ("url", "api_key", "model"),
    "ollama": ("url", "model"),
    "scuti": ("url", "token", "strategy", "window"),
    "freellmapi": ("url", "api_key", "model"),
}


def resolve(entry: dict[str, Any]) -> dict[str, Any]:
    """Copy of entry with each secret field of the form env:NAME replaced by that environment variable ("" when unset)."""
    out = dict(entry)
    for field in _SECRETS:
        if isinstance(value := out.get(field), str) and (ref := ENV_REF.fullmatch(value)):
            out[field] = os.environ.get(ref.group(1), "")
    return out


class GatewayStore:
    def __init__(self, path: str | Path, table: str = "gateways") -> None:
        """Entries are rows of `table` in the SQLite settings file `path`, one JSON document per gateway id."""
        self._path, self._table = Path(path), table
        self._lock = threading.Lock()

    def all(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {gid: resolve(entry) for gid, entry in self._read().items()}

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            data = settings_store.read_all(self._path, self._table)
        except (OSError, ValueError, sqlite3.Error):
            return {}
        return {gid: entry for gid, entry in data.items() if isinstance(entry, dict)}

    def public(self) -> list[dict[str, Any]]:
        return [self._public(gid, entry) for gid, entry in sorted(self.all().items())]

    @staticmethod
    def _public(gid: str, entry: dict[str, Any]) -> dict[str, Any]:
        out = {"id": gid, **{k: v for k, v in entry.items() if k not in _SECRETS}}
        resolved = resolve(entry)
        for secret, flag in _SECRETS.items():
            if secret in _FIELDS.get(entry.get("kind", ""), ()):
                out[flag] = bool(resolved.get(secret))
        return out

    def put(self, gid: Any, data: Any) -> dict[str, Any]:
        """Create or update one gateway. Raises ValueError with a message that is safe to show."""
        if not isinstance(gid, str) or not ID.fullmatch(gid):
            raise ValueError("The id must be 1 to 48 characters: lowercase letters, digits, - and _, starting with a letter or digit.")
        if not isinstance(data, dict):
            raise ValueError("Send an object.")
        kind = data.get("kind")
        if kind not in KINDS:
            raise ValueError("The kind must be typesafe, ollama, scuti or freellmapi.")
        with self._lock:
            gateways = self._read()
            old = gateways.get(gid, {}) if gateways.get(gid, {}).get("kind") == kind else {}
            entry = self._clean(kind, data, old)
            settings_store.put(self._path, self._table, gid, entry)
        return self._public(gid, entry)

    @staticmethod
    def _clean(kind: str, data: dict[str, Any], old: dict[str, Any]) -> dict[str, Any]:
        def text(key: str, label: str, required: bool, limit: int = 300) -> str | None:
            value = data.get(key, old.get(key))
            if value is None or value == "":
                if required:
                    raise ValueError(f"{label} is required.")
                return None
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError(f"{label} must be text of at most {limit} characters.")
            return value.strip()

        entry: dict[str, Any] = {"kind": kind}
        url = text("url", "The address", kind != "typesafe")
        url = (url or TYPESAFE_URL) if kind == "typesafe" else url
        url = url.rstrip("/")
        if not _valid_url(url):
            raise ValueError("The address must look like http://host:port, with no user name, query or fragment.")
        entry["url"] = url
        timeout = data.get("timeout_s", old.get("timeout_s", DEFAULT_TIMEOUT))
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 600:
            raise ValueError("The timeout must be a whole number of seconds from 1 to 600.")
        entry["timeout_s"] = timeout
        if kind == "typesafe":
            entry["model"] = text("model", "The model", True, 100)
            entry["api_key"] = text("api_key", "The API key", True, MAX_TOKEN)
        elif kind == "ollama":
            entry["model"] = text("model", "The model", True, 100)
        elif kind == "freellmapi":
            entry["model"] = text("model", "The model", False, 100) or ""  # empty: FreeLLMAPI picks a decision model
            entry["api_key"] = text("api_key", "The API key", True, MAX_TOKEN)
        else:
            if (token := text("token", "The token", False, MAX_TOKEN)) is not None:
                entry["token"] = token
            if (strategy := text("strategy", "The strategy", False, 60)) is not None:
                entry["strategy"] = strategy
            window = data.get("window", old.get("window"))
            if window is not None:
                if isinstance(window, bool) or not isinstance(window, int) or not 16 <= window <= 8192:
                    raise ValueError("The window must be a whole number from 16 to 8192.")
                entry["window"] = window
        return entry

    def delete(self, gid: str) -> bool:
        with self._lock:
            gateways = self._read()
            if gid not in gateways:
                return False
            settings_store.delete(self._path, self._table, gid)
            return True
