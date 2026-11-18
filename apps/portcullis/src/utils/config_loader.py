"""Config and secret file loading. A missing .env is copied from its .env.example; a missing config is an error."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from dotenv import dotenv_values

from src.citadel_auth import root_overrides



def _ensure_from_example(path: Path) -> bool:
    """Copies ``<path>.example`` to ``path`` if needed (a .env); False if neither exists."""
    if path.exists():
        return True
    example = path.with_name(path.name + ".example")
    if not example.exists():
        return False
    shutil.copyfile(example, path)
    return True


def load_json_config(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_env_secrets(path: str | Path) -> dict[str, str]:
    """A missing secret file (and example) is an empty dict, not an error."""
    path = Path(path)
    if not _ensure_from_example(path):
        return {}
    return {**{k: v for k, v in dotenv_values(path).items() if v is not None}, **root_overrides(path.parent)}
