"""Who gets a message: @mentions from the user, and (when relay is on) a worker handing a
turn to another worker with an @mention on the last line of its reply."""

from __future__ import annotations

import re
from dataclasses import dataclass

# An @handle that is not part of a longer word, address or handle.
_MENTION = re.compile(r"(?<![\w@])@([A-Za-z0-9_-]{1,24})(?![\w@-])")
_HANDOFF = re.compile(r"^@([A-Za-z0-9_-]{1,24})(?![\w@-])[:,]?\s*(.*)$")
_CONTINUE = "Please continue."


@dataclass(frozen=True)
class Member:
    worker_id: int
    label: str


class TurnRouter:
    def __init__(self, max_relay_depth: int = 3) -> None:
        self.max_relay_depth = max_relay_depth

    def target_for_user(self, text: str, members: list[Member], last_worker_id: int | None) -> Member | None:
        by_label = {member.label.lower(): member for member in members}
        for match in _MENTION.finditer(text):
            member = by_label.get(match.group(1).lower())
            if member is not None:
                return member
        for member in members:
            if member.worker_id == last_worker_id:
                return member
        return members[0] if len(members) == 1 else None

    def handoff(self, reply: str, members: list[Member], current_worker_id: int) -> tuple[Member, str] | None:
        """The worker a reply passes the turn to, and what to tell it, or None."""
        lines = [line.strip() for line in reply.strip().splitlines() if line.strip()]
        if not lines:
            return None
        match = _HANDOFF.match(lines[-1])
        if match is None:
            return None
        target = next((m for m in members if m.label.lower() == match.group(1).lower()), None)
        if target is None or target.worker_id == current_worker_id:
            return None
        return target, match.group(2).strip() or _CONTINUE
