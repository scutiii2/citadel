"""The token Portcullis presents to Scribe (dictation), kept in its settings database. Bard and the other tool services are reached
through Stronghold, which keeps their tokens (Stronghold Admin, Tool services).

Each tool service makes one token per caller on its own admin page (Tokens card). An administrator pastes it on the
Tool services page; it is saved in `settings.db` (table `tool_tokens`) and used by the next request. The token is
write-only: a view says only whether one is set. A token in the environment or `.env` is the starting value; a saved one wins.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.citadel_auth import settings_store

TABLE = "tool_tokens"
NAMES = ("scribe",)
LABELS = {"scribe": "Scribe"}


class TokenError(ValueError):
    """A change is refused; the message is safe to show."""


def stored(path: Path) -> dict[str, str]:
    return {name: token for name, token in settings_store.read_all(path, TABLE).items() if isinstance(token, str) and token}


def token_for(path: Path | None, name: str, fallback: str | None) -> str | None:
    """The saved token of `name`, else `fallback` (the environment's)."""
    return (stored(path).get(name) if path is not None else None) or fallback or None


def view(path: Path, current: dict[str, str | None]) -> dict[str, Any]:
    """Every tool service with whether a token is in use and whether it was saved here. Never the token."""
    saved = stored(path)
    return {"services": [
        {"name": name, "label": LABELS[name], "has_token": bool(current.get(name)), "stored": name in saved}
        for name in NAMES
    ]}


def update(path: Path, changes: Any) -> dict[str, str | None]:
    """Save `{name: token | None}` (None removes the saved token). Returns the new saved value per changed name.
    Nothing is saved if one change is refused."""
    if not isinstance(changes, dict) or not changes:
        raise TokenError("Send at least one token to change.")
    checked: dict[str, str | None] = {}
    for name, token in changes.items():
        if name not in NAMES:
            raise TokenError(f"Unknown tool service: {name}.")
        if token is not None and (not isinstance(token, str) or not token.strip() or len(token) > 500):
            raise TokenError(f"{LABELS[name]}: paste the token, or remove it.")
        checked[name] = None if token is None else token.strip()
    for name, token in checked.items():
        if token is None:
            settings_store.delete(path, TABLE, name)
        else:
            settings_store.put(path, TABLE, name, token)
    return checked
