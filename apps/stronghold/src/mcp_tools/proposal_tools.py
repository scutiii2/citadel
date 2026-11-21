"""Proposal tool. Every refusal is a result the model can read; nothing here raises to the model."""

from __future__ import annotations

from typing import Any

from src.brain.files import BrainError
from src.brain.proposals import BrainProposals
from src.mcp_tools.scope import Scope


class ProposalTools:
    def __init__(self, proposals: BrainProposals) -> None:
        self._proposals = proposals

    async def propose(self, scope: Scope, title: str, body: str, item_ids: list[int] | None,
                      folder: str, tags: list[str] | None) -> dict[str, Any]:
        try:
            made, waiting = await self._proposals.propose(scope.uid, scope.chat_id, title, body, item_ids or [], folder, tags or [])
        except BrainError as error:
            return {"ok": False, "message": str(error)}
        said = "That suggestion is already waiting for the user." if waiting else "Suggested."
        return {"ok": True, "proposal": {"id": made["id"], "title": made["title"]},
                "message": f"{said} The user decides in Ember; nothing is saved to long-term memory until they keep it."}
