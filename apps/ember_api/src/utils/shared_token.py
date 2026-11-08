"""The internal token every Citadel app shares, made once on first run so nobody sets it by hand.
The first app to start writes a random secret to INTERNAL_TOKEN_FILE (default ~/.citadel/internal_token; in Docker a shared volume); the others read it.
INTERNAL_API_TOKEN, when set, still wins. INTERNAL_TOKEN_FILE set to empty turns this off (tests, or a deliberately open loopback setup).
Keep this file identical in armory, legion, treasury and ember_api."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def shared_token() -> str:
    """The shared secret, created if missing. "" when switched off or the file cannot be written."""
    raw = os.environ.get("INTERNAL_TOKEN_FILE")
    if raw == "":
        return ""
    path = Path(raw) if raw else Path.home() / ".citadel" / "internal_token"
    try:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
            tmp.write_text(secrets.token_urlsafe(32), encoding="utf-8")
            try:
                os.link(tmp, path)  # atomic: a racing app either wins or finds the winner's complete file
            except FileExistsError:
                pass
            finally:
                tmp.unlink(missing_ok=True)
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
