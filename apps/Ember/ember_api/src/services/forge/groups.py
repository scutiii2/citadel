"""One account's Forge groups: titles, modes, and which of its workers are invited.

Every lookup filters by account, so another account's id behaves like a missing one."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ForgeGroup, ForgeGroupWorker, ForgeWorker
from src.services.forge.plans import PlanPolicyRegistry
from src.services.forge.protocol import MODES
from src.services.forge.workers import WorkerNotFound

TITLE_MAX = 80
FOLDER_MAX = 500
MAX_GROUPS_PER_ACCOUNT = 50
MAX_MEMBERS = 8


class GroupNotFound(Exception):
    """Unknown id, or another account's (deliberately indistinguishable)."""


class GroupLimitError(Exception):
    """Too many groups for the account (maps to 409)."""


class MemberLimitError(Exception):
    """The group has as many workers as it can hold (maps to 409)."""


class WorkerNotEligible(Exception):
    """The worker cannot be invited; `reason` is safe to show."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AlreadyMember(Exception):
    """The worker is already in the group."""


class NotAMember(Exception):
    """The worker is not in the group."""


class InvalidGroup(ValueError):
    """A title, mode or folder is not acceptable; the message is safe to show."""


@dataclass(frozen=True)
class MemberRow:
    worker: ForgeWorker
    folder: str
    last_seq: int


def _clean_title(title: str) -> str:
    cleaned = " ".join(title.split())
    if not cleaned:
        raise InvalidGroup("The title must not be blank")
    if len(cleaned) > TITLE_MAX:
        raise InvalidGroup(f"The title is at most {TITLE_MAX} characters")
    return cleaned


def _clean_mode(mode: str) -> str:
    if mode not in MODES:
        raise InvalidGroup(f"The mode must be one of: {', '.join(MODES)}")
    return mode


def _clean_folder(folder: str) -> str:
    cleaned = folder.strip()
    if not cleaned or "\x00" in cleaned:
        raise InvalidGroup("The folder must not be blank")
    if len(cleaned) > FOLDER_MAX:
        raise InvalidGroup(f"The folder is at most {FOLDER_MAX} characters")
    return cleaned


class GroupService:
    def __init__(self, session: AsyncSession, account_id: int, plans: PlanPolicyRegistry) -> None:
        self._session = session
        self._account_id = account_id
        self._plans = plans

    async def list(self) -> list[ForgeGroup]:
        """Newest first."""
        rows = await self._session.scalars(
            select(ForgeGroup).where(ForgeGroup.account_id == self._account_id).order_by(ForgeGroup.id.desc())
        )
        return list(rows)

    async def get(self, group_id: int) -> ForgeGroup:
        group = await self._session.scalar(
            select(ForgeGroup).where(ForgeGroup.id == group_id, ForgeGroup.account_id == self._account_id)
        )
        if group is None:
            raise GroupNotFound(group_id)
        return group

    async def create(self, title: str, mode: str = "ask") -> ForgeGroup:
        title, mode = _clean_title(title), _clean_mode(mode)
        count = await self._session.scalar(
            select(func.count()).select_from(ForgeGroup).where(ForgeGroup.account_id == self._account_id)
        )
        if (count or 0) >= MAX_GROUPS_PER_ACCOUNT:
            raise GroupLimitError(f"At most {MAX_GROUPS_PER_ACCOUNT} groups per account - delete some first")
        group = ForgeGroup(account_id=self._account_id, title=title, mode=mode)
        self._session.add(group)
        await self._session.commit()
        return group

    async def update(
        self, group_id: int, *, title: str | None = None, mode: str | None = None, relay: bool | None = None
    ) -> ForgeGroup:
        group = await self.get(group_id)
        if title is not None:
            group.title = _clean_title(title)
        if mode is not None:
            group.mode = _clean_mode(mode)
        if relay is not None:
            group.relay = relay
        await self._session.commit()
        return group

    async def delete(self, group_id: int) -> None:
        """Deletes the group; its members and messages go with it (foreign key cascade)."""
        group = await self.get(group_id)
        await self._session.execute(delete(ForgeGroup).where(ForgeGroup.id == group.id))
        await self._session.commit()

    async def members(self, group_id: int) -> list[MemberRow]:
        await self.get(group_id)
        rows = await self._session.execute(
            select(ForgeWorker, ForgeGroupWorker.folder, ForgeGroupWorker.last_seq)
            .join(ForgeGroupWorker, ForgeGroupWorker.worker_id == ForgeWorker.id)
            .where(ForgeGroupWorker.group_id == group_id)
            .order_by(ForgeWorker.id)
        )
        return [MemberRow(worker, folder, last_seq) for worker, folder, last_seq in rows]

    async def member(self, group_id: int, worker_id: int) -> MemberRow:
        for row in await self.members(group_id):
            if row.worker.id == worker_id:
                return row
        raise NotAMember(worker_id)

    async def invite(self, group_id: int, worker_id: int, folder: str) -> MemberRow:
        await self.get(group_id)
        worker = await self._session.scalar(
            select(ForgeWorker).where(ForgeWorker.id == worker_id, ForgeWorker.account_id == self._account_id)
        )
        if worker is None:
            raise WorkerNotFound(worker_id)
        folder = _clean_folder(folder)
        problem = await self._plans.problem(worker)
        if problem is not None:
            raise WorkerNotEligible(problem)
        current = await self.members(group_id)
        if any(row.worker.id == worker_id for row in current):
            raise AlreadyMember(worker_id)
        if len(current) >= MAX_MEMBERS:
            raise MemberLimitError(f"At most {MAX_MEMBERS} workers per group")
        self._session.add(ForgeGroupWorker(group_id=group_id, worker_id=worker_id, folder=folder, last_seq=0))
        await self._session.commit()
        return MemberRow(worker, folder, 0)

    async def set_folder(self, group_id: int, worker_id: int, folder: str) -> MemberRow:
        """Moves a member to another folder. Its next turn runs there."""
        row = await self.member(group_id, worker_id)
        folder = _clean_folder(folder)
        await self._session.execute(
            update(ForgeGroupWorker)
            .where(ForgeGroupWorker.group_id == group_id, ForgeGroupWorker.worker_id == worker_id)
            .values(folder=folder)
        )
        await self._session.commit()
        return MemberRow(row.worker, folder, row.last_seq)

    async def remove_member(self, group_id: int, worker_id: int) -> None:
        await self.member(group_id, worker_id)
        await self._session.execute(
            delete(ForgeGroupWorker).where(ForgeGroupWorker.group_id == group_id, ForgeGroupWorker.worker_id == worker_id)
        )
        await self._session.commit()

    async def mark_seen(self, group_id: int, worker_id: int, seq: int) -> None:
        """The worker has now seen messages up to `seq`, and was the last one addressed."""
        await self._session.execute(
            update(ForgeGroupWorker)
            .where(ForgeGroupWorker.group_id == group_id, ForgeGroupWorker.worker_id == worker_id)
            .values(last_seq=seq)
        )
        await self._session.execute(
            update(ForgeGroup)
            .where(ForgeGroup.id == group_id, ForgeGroup.account_id == self._account_id)
            .values(last_worker_id=worker_id)
        )
        await self._session.commit()

    async def problem(self, worker: ForgeWorker) -> str | None:
        """Why the worker cannot take a turn right now (its plan), or None."""
        return await self._plans.problem(worker)
