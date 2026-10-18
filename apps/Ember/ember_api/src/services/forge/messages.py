"""The transcript. Long-lived (it owns the per-group locks that keep `seq` gapless), so it
opens its own short sessions. It does not check ownership: callers verify the group with
GroupService first."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from src.db import Database
from src.models import ForgeMessage

LIST_LIMIT = 500
HISTORY_LIMIT = 40


def message_event(message: ForgeMessage) -> dict:
    """A stored message as the browser event (spec: Wire protocol, browser events)."""
    return {
        "type": "message",
        "seq": message.seq,
        "sender": message.sender,
        "kind": message.kind,
        "body": message.body,
        "created_at": message.created_at.isoformat(),
    }


class MessageStore:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, group_id: int) -> asyncio.Lock:
        return self._locks.setdefault(group_id, asyncio.Lock())

    async def append(self, group_id: int, sender: str, kind: str, body: dict) -> ForgeMessage:
        async with self._lock(group_id):
            async with self._database.sessions() as session:
                last = await session.scalar(
                    select(func.coalesce(func.max(ForgeMessage.seq), 0)).where(ForgeMessage.group_id == group_id)
                )
                message = ForgeMessage(group_id=group_id, seq=(last or 0) + 1, sender=sender, kind=kind, body=body)
                session.add(message)
                await session.commit()
                return message

    async def list_after(self, group_id: int, after: int = 0, limit: int = LIST_LIMIT) -> list[ForgeMessage]:
        async with self._database.sessions() as session:
            rows = await session.scalars(
                select(ForgeMessage)
                .where(ForgeMessage.group_id == group_id, ForgeMessage.seq > after)
                .order_by(ForgeMessage.seq)
                .limit(limit)
            )
            return list(rows)

    async def history(
        self, group_id: int, after_seq: int, *, exclude_seq: int | None = None, limit: int = HISTORY_LIMIT
    ) -> list[ForgeMessage]:
        """The newest `limit` text messages after `after_seq`, oldest first."""
        query = select(ForgeMessage).where(
            ForgeMessage.group_id == group_id, ForgeMessage.seq > after_seq, ForgeMessage.kind == "text"
        )
        if exclude_seq is not None:
            query = query.where(ForgeMessage.seq != exclude_seq)
        async with self._database.sessions() as session:
            rows = list(await session.scalars(query.order_by(ForgeMessage.seq.desc()).limit(limit)))
        rows.reverse()
        return rows

    async def last_seq(self, group_id: int) -> int:
        async with self._database.sessions() as session:
            last = await session.scalar(
                select(func.coalesce(func.max(ForgeMessage.seq), 0)).where(ForgeMessage.group_id == group_id)
            )
            return last or 0
