"""Per-account list of specialist agents the account switched off. Stored as one
document per account in db_gateway (collection "account_agents", key the account uid).
An id in the list means off; an account that never touched it has every agent on.

It holds only ids and does not know which agents exist: ai_agent owns that.
`blocked_names` turns the list into the entries ai_agent's tool filter understands.
"""

from __future__ import annotations

from src.db import utcnow
from src.services.db_gateway import DocumentStore

COLLECTION = "account_agents"
MAX_ITEMS = 200
# Mirrors ai_agent's core/tool_filter.AGENT_PREFIX.
AGENT_PREFIX = "agent:"


class TooManyItems(Exception):
    """The account already switched off MAX_ITEMS agents."""


class AccountAgentService:
    def __init__(self, store: DocumentStore, owner_uid: str) -> None:
        self._store = store
        self._owner = owner_uid

    async def disabled(self) -> list[str]:
        doc = await self._store.get(COLLECTION, self._owner) or {}
        return sorted(set(doc.get("disabled", [])))

    async def set_enabled(self, agent_id: str, enabled: bool) -> list[str]:
        """Switches one agent on or off and returns the whole disabled list. Read then
        write, not atomic: one account toggling from two tabs at the same instant can lose a change."""
        ids = set(await self.disabled())
        if not enabled and agent_id not in ids:
            if len(ids) >= MAX_ITEMS:
                raise TooManyItems
            ids.add(agent_id)
        elif enabled and agent_id in ids:
            ids.remove(agent_id)
        else:
            return sorted(ids)
        doc = {"owner": self._owner, "disabled": sorted(ids), "updated_at": utcnow().isoformat(timespec="seconds")}
        await self._store.put(COLLECTION, self._owner, doc)
        return doc["disabled"]


async def purge_owner(store: DocumentStore, owner_uid: str) -> None:
    """Forget one account's switched-off agents (used when the account is deleted)."""
    await store.delete(COLLECTION, owner_uid)


def blocked_names(disabled: list[str]) -> list[str]:
    """The tool-filter entries ai_agent reads as "this specialist is off"."""
    return [AGENT_PREFIX + agent_id for agent_id in disabled]
