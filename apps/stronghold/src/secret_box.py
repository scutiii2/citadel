"""Encrypting secrets at rest (a brain's API key, a private extension's headers), one Fernet token per value map.

The key comes from keys.py. If it is lost, stored secrets cannot be read and must be entered again.
"""

from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken


class SecretBoxError(Exception):
    """A key that is not valid, or a token that cannot be read. The message is safe to show."""


class SecretBox:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (ValueError, TypeError, UnicodeEncodeError):
            raise SecretBoxError("The secrets key in keys.json is not valid") from None

    def encrypt_map(self, values: dict[str, str]) -> str:
        payload = json.dumps(values, separators=(",", ":")).encode("utf-8")
        return self._fernet.encrypt(payload).decode("ascii")

    def decrypt_map(self, token: str) -> dict[str, str]:
        try:
            loaded = json.loads(self._fernet.decrypt(token.encode("ascii")))
        except (InvalidToken, ValueError, UnicodeError):
            raise SecretBoxError("The stored secret can't be read") from None
        if not isinstance(loaded, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in loaded.items()
        ):
            raise SecretBoxError("The stored secret can't be read")
        return loaded
