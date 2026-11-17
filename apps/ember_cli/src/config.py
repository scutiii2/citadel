"""chat_cli's settings: where portcullis is, and which account to log in as.

`configs/config_cli.json` is tracked; the password is never stored: it is typed at login.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parents[1] / "configs" / "config_cli.json"
DEFAULT_URL = "http://127.0.0.1:29601"


class ConfigError(Exception):
    """The settings file cannot be used; the message names the file."""


@dataclass(frozen=True)
class CliConfig:
    ember_api_url: str = DEFAULT_URL
    username: str = ""


def load_config(path: Path = CONFIG_FILE) -> CliConfig:
    """Reads the settings; the defaults are used when the file is missing."""
    if not path.is_file():
        return CliConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConfigError(f"{path}: cannot be read ({error})") from error
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: must hold a JSON object")
    url = raw.get("ember_api_url", DEFAULT_URL)
    username = raw.get("username", "")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ConfigError(f'{path}: "ember_api_url" must start with http:// or https://')
    if not isinstance(username, str):
        raise ConfigError(f'{path}: "username" must be text')
    return CliConfig(ember_api_url=url.rstrip("/"), username=username.strip())
