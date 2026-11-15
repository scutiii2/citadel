"""Stronghold's own keys, generated on first start and kept in `<data dir>/keys.json`.

`secrets` encrypts stored secrets (secret_box.py). The VAPID pair identifies Ember to
browsers' push services. Losing the file means saved calendar links must be entered again
and every browser must subscribe to push again; nothing else depends on it. Never logged.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid

FILE_NAME = "keys.json"


@dataclass(frozen=True)
class Keys:
    secrets: str
    vapid_private: str
    vapid_public: str


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _generate() -> Keys:
    vapid = Vapid()
    vapid.generate_keys()
    return Keys(
        secrets=Fernet.generate_key().decode("ascii"),
        vapid_private=_b64(vapid.private_key.private_numbers().private_value.to_bytes(32, "big")),
        vapid_public=_b64(vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)),
    )


def load_keys(data_dir: Path) -> Keys:
    """The keys in `data_dir`, made and written there first when the file is missing.
    A file that cannot be read is an error, never silently replaced: that would orphan stored secrets."""
    path = data_dir / FILE_NAME
    if path.exists():
        try:
            return Keys(**json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, TypeError) as error:
            raise RuntimeError(f"{path} is not a valid keys file; restore it from a backup or remove it") from error
    keys = _generate()
    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(keys)), encoding="utf-8")
    os.chmod(path, 0o600)  # no effect on Windows; the folder is private to the service there
    return keys
