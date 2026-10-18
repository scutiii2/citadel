"""Pairing a worker to an account, and recognizing a worker that connects.

A pairing token is shown once. Only its SHA-256 is stored: the token is long and
random, so a plain hash is enough and lookups are by hash."""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import utcnow
from src.models import ForgeWorker
from src.services.forge.protocol import PROVIDERS

TOKEN_PREFIX = "ft_"
MAX_WORKERS_PER_ACCOUNT = 10
_LABEL = re.compile(r"^[a-z0-9_-]{1,24}$")
_PLAN_MAX = 80  # forge_workers.reported_plan


class WorkerNotFound(Exception):
    """Unknown id, or another account's (deliberately indistinguishable)."""


class WorkerLimitError(Exception):
    """Too many workers for the account (maps to 409)."""


class WorkerLabelTaken(Exception):
    """Another worker of this account already has the label."""


class InvalidWorkerLabel(ValueError):
    """The label is not a valid @mention handle; the message is safe to show."""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clean_label(label: str) -> str:
    cleaned = label.strip().lower()
    if not _LABEL.fullmatch(cleaned):
        raise InvalidWorkerLabel("A label is 1 to 24 letters, digits, - or _")
    return cleaned


@dataclass(frozen=True)
class NewWorker:
    worker: ForgeWorker
    token: str  # shown to the user once


class WorkerPairingService:
    """One account's workers."""

    def __init__(self, session: AsyncSession, account_id: int) -> None:
        self._session = session
        self._account_id = account_id

    async def list(self) -> list[ForgeWorker]:
        rows = await self._session.scalars(
            select(ForgeWorker).where(ForgeWorker.account_id == self._account_id).order_by(ForgeWorker.id)
        )
        return list(rows)

    async def get(self, worker_id: int) -> ForgeWorker:
        worker = await self._session.scalar(
            select(ForgeWorker).where(ForgeWorker.id == worker_id, ForgeWorker.account_id == self._account_id)
        )
        if worker is None:
            raise WorkerNotFound(worker_id)
        return worker

    async def create(self, provider: str, label: str) -> NewWorker:
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")
        label = clean_label(label)
        count = await self._session.scalar(
            select(func.count()).select_from(ForgeWorker).where(ForgeWorker.account_id == self._account_id)
        )
        if (count or 0) >= MAX_WORKERS_PER_ACCOUNT:
            raise WorkerLimitError(f"At most {MAX_WORKERS_PER_ACCOUNT} workers per account - remove some first")
        taken = await self._session.scalar(
            select(ForgeWorker.id).where(ForgeWorker.account_id == self._account_id, ForgeWorker.label == label)
        )
        if taken is not None:
            raise WorkerLabelTaken(label)
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        worker = ForgeWorker(account_id=self._account_id, provider=provider, label=label, token_hash=hash_token(token))
        self._session.add(worker)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise WorkerLabelTaken(label) from error
        return NewWorker(worker, token)

    async def delete(self, worker_id: int) -> ForgeWorker:
        """Revokes the worker: the row goes, and so do its group memberships."""
        worker = await self.get(worker_id)
        await self._session.execute(delete(ForgeWorker).where(ForgeWorker.id == worker.id))
        await self._session.commit()
        return worker


class WorkerAuthenticator:
    """Recognizes a connecting worker by its token. Not scoped to an account."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def authenticate(self, token: str) -> ForgeWorker | None:
        if not token.startswith(TOKEN_PREFIX):
            return None
        return await self._session.scalar(select(ForgeWorker).where(ForgeWorker.token_hash == hash_token(token)))

    async def record_hello(self, worker_id: int, plan: str | None) -> None:
        cleaned = " ".join(plan.split())[:_PLAN_MAX] if plan else None
        await self._session.execute(
            update(ForgeWorker).where(ForgeWorker.id == worker_id).values(reported_plan=cleaned or None, last_seen=utcnow())
        )
        await self._session.commit()

    async def touch(self, worker_id: int) -> None:
        await self._session.execute(update(ForgeWorker).where(ForgeWorker.id == worker_id).values(last_seen=utcnow()))
        await self._session.commit()
