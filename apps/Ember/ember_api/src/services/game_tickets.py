"""Short-lived single-use launch tickets; plaintext exists only at issuance."""
from __future__ import annotations
import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.db import utcnow
from src.models import GameTicket


class TicketService:
    def __init__(self, session: AsyncSession, now: Callable[[], datetime] = utcnow, lifetime: timedelta = timedelta(seconds=60)) -> None:
        self._session = session
        self._now = now
        self._lifetime = lifetime

    async def issue(self, game_id: str, account_id: int) -> str:
        now = self._now()
        await self._session.execute(delete(GameTicket).where(GameTicket.expires_at < now - timedelta(minutes=1)))
        ticket = secrets.token_urlsafe(32)
        self._session.add(GameTicket(token_hash=hashlib.sha256(ticket.encode()).hexdigest(), game_id=game_id,
                                     account_id=account_id, expires_at=now + self._lifetime))
        await self._session.commit()
        return ticket

    async def redeem(self, game_id: str, ticket: str) -> int | None:
        now = self._now()
        result = await self._session.execute(
            update(GameTicket)
            .where(GameTicket.token_hash == hashlib.sha256(ticket.encode()).hexdigest(),
                   GameTicket.game_id == game_id, GameTicket.used_at.is_(None), GameTicket.expires_at > now)
            .values(used_at=now).returning(GameTicket.account_id)
        )
        account_id = result.scalar_one_or_none()
        await self._session.commit()
        return account_id
