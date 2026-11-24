"""Whether every tool run needs a person's approval, kept in `.data/armory/settings.db` (table `policy`).

Armory owns this rule because it holds the tools. An administrator switches it on the Tool approval page of Armory
Admin. Portcullis reads it for each answer it starts and passes it on, and Ember shows it. A setting nobody changed
is off.
"""

from __future__ import annotations

from pathlib import Path

from src.citadel_auth import settings_store

TABLE = "policy"
FORCE_TOOL_APPROVAL = "force_tool_approval"


def forced(path: Path) -> bool:
    """True while every answer must ask before each tool runs, whatever the person chose."""
    return settings_store.read_all(path, TABLE).get(FORCE_TOOL_APPROVAL) is True


def is_stored(path: Path) -> bool:
    """False until an administrator (or a migration from Portcullis) saved the switch once."""
    return FORCE_TOOL_APPROVAL in settings_store.read_all(path, TABLE)


def set_forced(path: Path, value: bool) -> bool:
    """Saves the switch and returns what it was before."""
    before = forced(path)
    settings_store.put(path, TABLE, FORCE_TOOL_APPROVAL, value)
    return before
