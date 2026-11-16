"""Stronghold's own key, generated on first start and kept in `<data dir>/keys.json`.

`secrets` encrypts stored secrets (secret_box.py). Losing the file means saved brain keys and
private-extension headers must be entered again; nothing else depends on it. Never logged.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.fernet import Fernet

FILE_NAME = "keys.json"


@dataclass(frozen=True)
class Keys:
    secrets: str


def load_keys(data_dir: Path) -> Keys:
    """The keys in `data_dir`, made and written there first when the file is missing.
    A file that cannot be read is an error, never silently replaced: that would orphan stored secrets.
    Older files also hold a web-push key pair; it is ignored (and left in place)."""
    path = data_dir / FILE_NAME
    if path.exists():
        try:
            return Keys(secrets=json.loads(path.read_text(encoding="utf-8"))["secrets"])
        except (ValueError, TypeError, KeyError) as error:
            raise RuntimeError(f"{path} is not a valid keys file; restore it from a backup or remove it") from error
    keys = Keys(secrets=Fernet.generate_key().decode("ascii"))
    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(keys)), encoding="utf-8")
    os.chmod(path, 0o600)  # no effect on Windows; the folder is private to the service there
    return keys
