"""Config/secret file loading with auto-created real files.

Same behavior as chat_app/src/utils/config_loader.py: a missing real file is
copied from its committed ``.example`` twin on first use instead of failing.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from dotenv import dotenv_values

from src.utils.shared_token import shared_token


def _ensure_from_example(path: Path) -> bool:
    """Copies ``<path>.example`` to ``path`` if needed; False if neither exists."""
    if path.exists():
        return True
    example = path.with_name(path.name + ".example")
    if not example.exists():
        return False
    shutil.copyfile(example, path)
    return True


def load_json_config(path: str | Path) -> dict:
    path = Path(path)
    if not _ensure_from_example(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_env_secrets(path: str | Path) -> dict[str, str]:
    """A missing secret file (and example) is an empty dict, not an error."""
    path = Path(path)
    if not _ensure_from_example(path):
        return {}
    return {k: v for k, v in dotenv_values(path).items() if v is not None}


def internal_token(path: str | Path) -> str:
    """INTERNAL_API_TOKEN from the environment, else the secret file, else the shared token file. "" = not configured."""
    return os.getenv("INTERNAL_API_TOKEN") or load_env_secrets(path).get("INTERNAL_API_TOKEN") or shared_token()


def service_token(path: str | Path, name: str) -> str:
    """The token a tool service (Bard, Scribe...) issued to this app: `<NAME>_TOKEN` from the environment, else the secret file.
    Tool services keep their own per-caller tokens, so the shared internal token is not a fallback. "" = not configured."""
    key = f"{name.upper()}_TOKEN"
    return os.getenv(key) or load_env_secrets(path).get(key) or ""
