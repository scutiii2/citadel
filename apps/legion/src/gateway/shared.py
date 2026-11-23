"""Small helpers both gateways use: atomic JSON files and the address check."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

MAX_URL = 300
MAX_TOKEN = 500


def load(path: str | os.PathLike[str]) -> dict:
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def replace(path: str | os.PathLike[str], data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), "utf-8")
    os.replace(temp, path)


def valid_url(url: str) -> bool:
    parts = urlsplit(url)
    return (len(url) <= MAX_URL and parts.scheme in ("http", "https") and bool(parts.hostname)
            and not parts.username and not parts.password and not parts.fragment and not parts.query)
