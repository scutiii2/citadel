"""Which chats of an account have an answer being written right now. Stronghold runs the turns."""

from __future__ import annotations

import json

from src.models import Account
from src.services.stronghold_forwarder import StrongholdForwarder, StrongholdUnavailable


async def running_chat_ids(stronghold: StrongholdForwarder, account: Account) -> set[str]:
    """Raises StrongholdUnavailable (502): guessing "none" would let a write land in a running chat."""
    answer = await stronghold.forward("GET", "/turns/running", account)
    try:
        return set(json.loads(answer.body)["chat_ids"])
    except (ValueError, KeyError, TypeError) as error:
        raise StrongholdUnavailable("unreadable running list") from error
