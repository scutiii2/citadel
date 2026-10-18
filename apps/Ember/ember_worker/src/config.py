"""Worker settings. The Ember address and options live in configs/config_worker.json (a
missing file is made from its .example twin); pairing tokens live in .env, one per provider."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("claude", "codex")
SOCKET_PATH = "/api/forge/worker"
DEFAULT_HEARTBEAT_SECONDS = 20.0


class ConfigError(Exception):
    """Something the user has to fix; the message says what."""


def token_key(provider: str) -> str:
    return f"EMBER_WORKER_TOKEN_{provider.upper()}"


@dataclass(frozen=True)
class WorkerConfig:
    url: str
    heartbeat_seconds: float
    plan_override: dict[str, str]
    tokens: dict[str, str]

    @property
    def socket_url(self) -> str:
        if self.url.startswith("https://"):
            return "wss://" + self.url[len("https://"):] + SOCKET_PATH
        if self.url.startswith("http://"):
            return "ws://" + self.url[len("http://"):] + SOCKET_PATH
        raise ConfigError(f"The Ember address must start with http:// or https:// (it is {self.url!r})")

    def paired_providers(self) -> list[str]:
        return [provider for provider in PROVIDERS if self.tokens.get(provider)]


class EnvFile:
    """A small KEY=VALUE file. Setting one key keeps every other line, comments included."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if not self._path.exists():
            return values
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values

    def set(self, key: str, value: str) -> None:
        lines = self._path.read_text(encoding="utf-8").splitlines() if self._path.exists() else []
        for index, line in enumerate(lines):
            if not line.lstrip().startswith("#") and line.partition("=")[0].strip() == key:
                lines[index] = f"{key}={value}"
                break
        else:
            lines.append(f"{key}={value}")
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def config_path(root: Path = ROOT) -> Path:
    return root / "configs" / "config_worker.json"


def _read_json(root: Path) -> dict:
    path = config_path(root)
    example = path.with_name(path.name + ".example")
    if not path.exists():
        if not example.exists():
            raise ConfigError(f"{path} is missing and so is its .example twin")
        shutil.copyfile(example, path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ConfigError(f"{path} is not valid JSON ({error})") from error
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must hold a JSON object")
    return data


def load_config(root: Path = ROOT) -> WorkerConfig:
    data = _read_json(root)
    url = str(data.get("url", "")).strip().rstrip("/")
    if not url:
        raise ConfigError("config_worker.json needs a url (the address of ember_api)")
    try:
        heartbeat = float(data.get("heartbeat_seconds", DEFAULT_HEARTBEAT_SECONDS))
    except (TypeError, ValueError) as error:
        raise ConfigError("heartbeat_seconds must be a number") from error
    if heartbeat <= 0:
        raise ConfigError("heartbeat_seconds must be above zero")
    overrides = {
        provider: str(value).strip()
        for provider, value in (data.get("plan_override") or {}).items()
        if provider in PROVIDERS and str(value).strip()
    }
    file_values = EnvFile(root / ".env").read()
    tokens = {}
    for provider in PROVIDERS:
        token = os.environ.get(token_key(provider)) or file_values.get(token_key(provider), "")
        if token:
            tokens[provider] = token
    return WorkerConfig(url, heartbeat, overrides, tokens)


def save_pairing(root: Path, provider: str, url: str, token: str, plan: str | None = None) -> None:
    """Remembers the Ember address and plan note in the config, and the token in .env."""
    data = _read_json(root)
    data["url"] = url.strip().rstrip("/")
    overrides = dict(data.get("plan_override") or {})
    if plan and plan.strip():
        overrides[provider] = plan.strip()
    data["plan_override"] = overrides
    config_path(root).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    EnvFile(root / ".env").set(token_key(provider), token)
