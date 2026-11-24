"""Gateway secrets are stored encrypted in settings.db: an API key or token is `enc:v1:<token>`, never plain text.

The key is LEGION_SECRET_KEY (a Fernet key) when set; otherwise a key file `secret.key` in Legion's data folder, made
on first use and readable by the owner only. Keep that file out of any backup that holds settings.db: together they
open the secrets. A value that is not sealed (older rows, `env:NAME` references) is read as it is and sealed the next
time its gateway is saved, or when the stores are first opened (`seal_rows`).
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from src.citadel_auth import data_dir

PREFIX = "enc:v1:"
KEY_FILE = data_dir(Path(__file__).resolve().parents[2]) / "secret.key"
_ENV_REF = re.compile(r"env:[A-Z][A-Z0-9_]{0,63}")
_lock = threading.Lock()
_fernet: Fernet | None = None


def _key() -> bytes:
    if env := os.environ.get("LEGION_SECRET_KEY"):
        return env.encode()
    if KEY_FILE.is_file():
        return KEY_FILE.read_bytes().strip()
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    descriptor = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        file.write(key)
    return key


def _cipher() -> Fernet:
    global _fernet
    with _lock:
        if _fernet is None:
            _fernet = Fernet(_key())
        return _fernet


def reset() -> None:
    """Forget the loaded key (tests, or after the key setting changed)."""
    global _fernet
    _fernet = None


def is_sealed(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def seal(value: str) -> str:
    """`value` encrypted. An `env:NAME` reference stays as it is: it holds no secret."""
    if not value or is_sealed(value) or _ENV_REF.fullmatch(value):
        return value
    return PREFIX + _cipher().encrypt(value.encode()).decode()


def unseal(value: str) -> str:
    """The plain text of a sealed value; any other value comes back unchanged. A sealed value that this key cannot
    open (the key changed) reads as empty, so the gateway shows as having no key rather than sending garbage."""
    if not is_sealed(value):
        return value
    try:
        return _cipher().decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken:
        return ""


def seal_fields(entry: dict[str, Any], fields: Any) -> dict[str, Any]:
    return {key: (seal(value) if key in fields and isinstance(value, str) else value) for key, value in entry.items()}


def unseal_fields(entry: dict[str, Any], fields: Any) -> dict[str, Any]:
    return {key: (unseal(value) if key in fields and isinstance(value, str) else value) for key, value in entry.items()}
