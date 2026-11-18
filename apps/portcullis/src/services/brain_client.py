"""Portcullis's view of an account's brain destinations, which Stronghold keeps.

Auto-save (second brain) only needs one fact: may this account write to this destination now?
Stronghold answers it from the encrypted connection and the account's current permissions.
"""

from __future__ import annotations

import json

from src.models import Account
from src.services.stronghold_forwarder import StrongholdForwarder

PUBLISH = "brain.instance.publish"


class BrainError(Exception):
    """A destination that cannot be written to (or checked)."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


class RemoteBrains:
    def __init__(self, stronghold: StrongholdForwarder, account: Account) -> None:
        self._stronghold = stronghold
        self._account = account

    async def resolve(self, scope: str, uid: str, *, write: bool, publish: bool) -> dict:
        """Stronghold decides from the account's current permissions; `uid` and `publish` are only
        kept so this answers like the connection store it replaces. Raises BrainError when not writable."""
        answer = await self._stronghold.forward("GET", f"/brains/writable/{scope}", self._account)
        if answer.status != 200 or not json.loads(answer.body).get("writable"):
            raise BrainError("This brain destination cannot be written to", 409)
        return {"scope": scope}
