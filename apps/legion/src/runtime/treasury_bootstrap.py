"""Where Treasury is, and the names Legion's settings carry in it.

Where Treasury itself is: `treasury_address()`, from TREASURY_URL or tracked config_app.json.
"""

from __future__ import annotations

import json
import os

INSTANCE = "legion"
CONNECTION = "data"
DEFAULT_TREASURY_URL = "http://127.0.0.1:29602"


def treasury_address() -> str:
    """The only bootstrap address: TREASURY_URL, config_app.json, then local default."""
    from src.runtime import config_files

    override = os.getenv("TREASURY_URL")
    if override:
        return override.strip().rstrip("/")
    path = config_files.CONFIGS_DIR / "config_app.json"
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return str(raw.get("treasury_url") or DEFAULT_TREASURY_URL).strip().rstrip("/")
