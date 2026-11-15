"""Portcullis's view of token usage, which Stronghold keeps.

Every chat turn, summary, suggestion, triage question and brain review asks `check()` first and
`record()` after. A check that cannot be answered is refused (503): without it a limit could not
be kept. A record that cannot be stored is logged and dropped, so the user still gets the answer.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.models import Account
from src.services.stronghold_forwarder import StrongholdForwarder, StrongholdUnavailable
from src.services.usage_rows import stored_rows

logger = logging.getLogger(__name__)


class UsageUnavailable(Exception):
    """Stronghold could not say whether the account is under its token limits."""


@dataclass(frozen=True)
class LimitBlock:
    reason: str
    reset_at: datetime


class UsageClient:
    def __init__(self, stronghold: StrongholdForwarder, account: Account) -> None:
        self._stronghold = stronghold
        self._account = account

    async def check(self) -> LimitBlock | None:
        """The limit the account has reached, or None."""
        try:
            answer = await self._stronghold.forward("POST", "/usage/check", self._account, json={})
            if answer.status != 200:
                raise UsageUnavailable(f"stronghold answered {answer.status}")
            block = json.loads(answer.body)["block"]
        except (StrongholdUnavailable, ValueError, KeyError) as error:
            raise UsageUnavailable(type(error).__name__) from error
        return LimitBlock(block["reason"], datetime.fromisoformat(block["reset_at"])) if block else None

    async def record(self, turn_id: str, kind: str, chat_id: str | None, result: dict[str, Any]) -> None:
        """Stores the tokens `result` spent. Never raises."""
        rows = stored_rows(result)
        if not rows:
            return
        try:
            answer = await self._stronghold.forward(
                "POST", "/usage/records", self._account,
                json={"turn_id": turn_id, "kind": kind, "chat_id": chat_id, "rows": rows})
            failed = None if answer.status == 201 else f"status {answer.status}"
        except StrongholdUnavailable as error:
            failed = str(error)
        if failed:  # Accounting must not lose the user's answer.
            logger.warning("recording usage of %s %s failed (%s)", kind, turn_id, failed)
