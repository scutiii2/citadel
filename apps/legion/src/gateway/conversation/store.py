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
from src.gateway.conversation.contract import TIERS
from src.gateway.conversation.gateways.base import CAPABILITIES

ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}")
DEFAULT_TIMEOUT = 300
SECRETS = {"api_key": "has_api_key", "token": "has_token", "aws_access_key_id": "has_aws_access_key_id",
           "aws_secret_access_key": "has_aws_secret_access_key"}

# provider -> variant -> (field, label, secret, required). The page draws these; the store checks them.
PROVIDERS: dict[str, dict[str, list[tuple[str, str, bool, bool]]]] = {
    "anthropic": {
        "key": [("api_key", "API key", True, True), ("base_url", "Base address (gateways such as OpenRouter)", False, False)],
        "bedrock": [("aws_region", "AWS region", False, True), ("aws_access_key_id", "AWS access key id", True, True),
                    ("aws_secret_access_key", "AWS secret access key", True, True)],
        "vertex": [("project_id", "Google project id", False, True), ("region", "Region", False, True)],
    },
    "openai": {
        "key": [("api_key", "API key", True, False), ("base_url", "Base address (empty = OpenAI)", False, False)],
        "azure": [("azure_endpoint", "Azure endpoint", False, True), ("api_version", "API version", False, True), ("api_key", "API key", True, True)],
    },
    "scuti": {"": [("url", "Model service address", False, True), ("token", "Token", True, False), ("project", "Project model", False, False)]},
}
FORM = {"providers": PROVIDERS, "choices": {"api": ["chat", "responses"], "max_tokens_param": ["max_tokens", "max_completion_tokens"]}}
ADDRESS = {"base_url", "azure_endpoint", "url"}
ENV_REF = re.compile(r"env:([A-Z][A-Z0-9_]{0,63})")


def resolve(entry: dict[str, Any]) -> dict[str, Any]:
    """Copy of entry with each secret field of the form env:NAME replaced by that environment variable ("" when unset)."""
    out = dict(entry)
    for field in SECRETS:
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
        out = {"id": gid, **{k: v for k, v in entry.items() if k not in SECRETS}}
        resolved = resolve(entry)
        for secret, flag in SECRETS.items():
            if any(secret == f[0] for variant in PROVIDERS.get(entry.get("provider", ""), {}).values() for f in variant):
                out[flag] = bool(resolved.get(secret))
        return out

    def put(self, gid: Any, data: Any) -> dict[str, Any]:
        """Create or update one gateway. Raises ValueError with a message that is safe to show."""
        if not isinstance(gid, str) or not ID.fullmatch(gid):
            raise ValueError("The id must be 1 to 48 characters: lowercase letters, digits, - and _, starting with a letter or digit.")
        if not isinstance(data, dict):
            raise ValueError("Send an object.")
        provider = data.get("provider")
        if not isinstance(provider, str) or provider not in PROVIDERS:
            raise ValueError("The provider must be anthropic, openai or scuti.")
        with self._lock:
            gateways = self._read()
            old = gateways.get(gid, {}) if gateways.get(gid, {}).get("provider") == provider else {}
            entry = self._clean(provider, data, old)
            settings_store.put(self._path, self._table, gid, entry)
        return self._public(gid, entry)

    @staticmethod
    def _clean(provider: str, data: dict[str, Any], old: dict[str, Any]) -> dict[str, Any]:
        def pick(key: str) -> Any:
            return data.get(key, old.get(key))

        def text(key: str, label: str, required: bool, limit: int = 300) -> str | None:
            value = pick(key)
            if isinstance(value, str):
                value = value.strip()
            if value is None or value == "":
                if required:
                    raise ValueError(f"{label} is required.")
                return None
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError(f"{label} must be text of at most {limit} characters.")
            return value.strip()

        entry: dict[str, Any] = {"provider": provider}
        variants = PROVIDERS[provider]
        if provider != "scuti":
            auth = pick("auth") or "key"
            if not isinstance(auth, str) or auth not in variants:
                raise ValueError("The auth must be " + " or ".join(variants) + ".")
            entry["auth"] = auth
        else:
            auth = ""
        for field, label, secret, required in variants[auth]:
            if provider == "openai" and field == "api_key" and auth == "key":
                required = False
            value = text(field, label, required, MAX_TOKEN if secret else 300)
            if value is None:
                continue
            if field in ADDRESS:
                value = value.rstrip("/")
                if not _valid_url(value):
                    raise ValueError(f"{label}: the address must look like http://host:port, with no user name, query or fragment.")
            entry[field] = value
        if provider == "openai" and auth == "key" and not entry.get("base_url") and not entry.get("api_key"):
            raise ValueError("A key is required for OpenAI itself; a local server needs a base address instead.")
        if provider == "openai":
            api = pick("api") or "chat"
            if api not in ("chat", "responses"):
                raise ValueError("The api must be chat or responses.")
            entry["api"] = api
            param = pick("max_tokens_param")
            if param is not None:
                if param not in ("max_tokens", "max_completion_tokens"):
                    raise ValueError("The max_tokens_param must be max_tokens or max_completion_tokens.")
                entry["max_tokens_param"] = param
            usage = pick("stream_usage")
            if usage is not None:
                if not isinstance(usage, bool):
                    raise ValueError("stream_usage must be true or false.")
                entry["stream_usage"] = usage
        if (model := text("model", "The model", provider != "scuti", 200)) is not None:
            entry["model"] = model
        models = pick("models")
        if models is not None:
            if (not isinstance(models, dict) or set(models) - set(TIERS) or provider == "scuti"
                    or not all(isinstance(v, str) and len(v.strip()) <= 200 for v in models.values())):
                raise ValueError("The models are text of at most 200 characters for: " + ", ".join(TIERS) + " (not for a Scuti service).")
            if models := {k: v.strip() for k, v in models.items() if v.strip()}:
                entry["models"] = models
        if (label := text("label", "The label", False, 80)) is not None:
            entry["label"] = label
        timeout = pick("timeout_s") if pick("timeout_s") is not None else DEFAULT_TIMEOUT
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 1800:
            raise ValueError("The timeout must be a whole number of seconds from 1 to 1800.")
        entry["timeout_s"] = timeout
        for key in ("default_max_tokens", "max_tokens_limit"):
            value = pick(key)
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1_000_000:
                    raise ValueError(f"{key} must be a whole number from 1 to 1000000.")
                entry[key] = value
        caps = pick("capabilities")
        if caps is not None:
            if not isinstance(caps, dict) or set(caps) - set(CAPABILITIES) or not all(isinstance(v, bool) for v in caps.values()):
                raise ValueError("The capabilities are true or false for: " + ", ".join(CAPABILITIES) + ".")
            entry["capabilities"] = caps
        return entry

    def delete(self, gid: str) -> bool:
        with self._lock:
            gateways = self._read()
            if gid not in gateways:
                return False
            settings_store.delete(self._path, self._table, gid)
            return True
