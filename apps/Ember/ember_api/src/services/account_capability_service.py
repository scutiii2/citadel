"""Per-account choice of which built-in capabilities and server-listed
extensions the account has added. Stored as one document per account in db_gateway
(collection "account_capabilities", key the account uid). An id in the lists means enabled;
the service never stores a "disabled" entry.

It holds only ids and does not know which ones exist: the browser and mcp_server
own that. `tools_to_disable` is the one place that looks at mcp_server's list.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

from src.db import utcnow
from src.services.db_gateway import DocumentStore

Kind = Literal["capability", "extension"]
COLLECTION = "account_capabilities"
MAX_ITEMS = 200
_SCAN_PAGE = 500
_SCAN_MAX_PAGES = 20


class TooManyItems(Exception):
    """The account already has MAX_ITEMS things added."""


@dataclass(frozen=True)
class AccountCapabilities:
    capabilities: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)


class AccountCapabilityService:
    def __init__(self, store: DocumentStore, owner_uid: str) -> None:
        self._store = store
        self._owner = owner_uid

    async def get(self) -> AccountCapabilities:
        doc = await self._store.get(COLLECTION, self._owner) or {}
        return AccountCapabilities(
            capabilities=sorted(set(doc.get("capabilities", []))), extensions=sorted(set(doc.get("extensions", [])))
        )

    async def set_enabled(self, kind: Kind, item_id: str, enabled: bool) -> AccountCapabilities:
        """Adds or removes one id and returns the whole set. Asking for the state it already
        has changes nothing. Read then write, not atomic: one account toggling from two tabs
        at the same instant can lose a change."""
        state = await self.get()
        side = "capabilities" if kind == "capability" else "extensions"
        ids = set(getattr(state, side))
        if enabled and item_id not in ids:
            if len(state.capabilities) + len(state.extensions) >= MAX_ITEMS:
                raise TooManyItems
            ids.add(item_id)
        elif not enabled and item_id in ids:
            ids.remove(item_id)
        else:
            return state
        changed = replace(state, **{side: sorted(ids)})
        doc = {
            "owner": self._owner, "capabilities": changed.capabilities, "extensions": changed.extensions,
            "updated_at": utcnow().isoformat(timespec="seconds"),
        }
        await self._store.put(COLLECTION, self._owner, doc)
        return changed


async def forget_extension(store: DocumentStore, extension_id: str) -> None:
    """Drops an extension from every account (it was removed from mcp_server)."""
    offset = 0
    for _ in range(_SCAN_MAX_PAGES):
        docs = await store.query(COLLECTION, {}, limit=_SCAN_PAGE, offset=offset)
        for doc in docs:
            if extension_id in doc.get("extensions", []):
                doc["extensions"] = [e for e in doc["extensions"] if e != extension_id]
                await store.put(COLLECTION, doc["owner"], doc)
        if len(docs) < _SCAN_PAGE:
            break
        offset += _SCAN_PAGE


async def purge_owner(store: DocumentStore, owner_uid: str) -> None:
    """Forget one account's added items (used when the account is deleted)."""
    await store.delete(COLLECTION, owner_uid)


def tools_to_disable(capabilities: list[dict[str, Any]], enabled: list[str]) -> list[str]:
    """The sorted tool names of every capability in mcp_server's list that is
    not in `enabled`. Extension tools are not capabilities and are never listed."""
    on = set(enabled)
    names = {
        tool
        for capability in capabilities
        if isinstance(capability, dict) and capability.get("name") not in on
        for tool in capability.get("tools", [])
        if isinstance(tool, str)
    }
    return sorted(names)
