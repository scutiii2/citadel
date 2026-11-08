"""Unread state is local; ownership is always checked by the upstream service."""

from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ticket_activity import AccountTicketSeen, TicketStaffActivity


class TicketUnreadService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def unread_ids(
        self, account_id: int, ticket_ids: list[int], activity_times: dict[int, str | None] | None = None,
    ) -> set[int]:
        """Only inspect the tickets returned by an ownership-scoped upstream list."""
        if not ticket_ids:
            return set()
        if activity_times:
            await self.reconcile(activity_times)
        activity, seen = TicketStaffActivity, AccountTicketSeen
        query = (
            select(activity.ticket_id)
            .outerjoin(seen, and_(seen.ticket_id == activity.ticket_id, seen.account_id == account_id))
            .where(activity.ticket_id.in_(ticket_ids))
            .where(or_(seen.last_seen_at.is_(None), activity.last_staff_activity_at > seen.last_seen_at))
        )
        return set((await self.session.scalars(query)).all())

    async def mark_seen(self, account_id: int, ticket_id: int, fetched_at: datetime) -> None:
        """A read covers activity before the fetch began, never a newer staff reply."""
        statement = insert(AccountTicketSeen).values(
            account_id=account_id, ticket_id=ticket_id, last_seen_at=fetched_at,
        )
        await self.session.execute(statement.on_conflict_do_update(
            index_elements=["account_id", "ticket_id"],
            set_={"last_seen_at": func.max(AccountTicketSeen.last_seen_at, statement.excluded.last_seen_at)},
        ))
        await self.session.commit()

    async def reconcile(self, activity_times: dict[int, str | None]) -> None:
        """Persist upstream activity times, including changes made outside Ember."""
        rows = []
        for ticket_id, value in activity_times.items():
            if value is None:
                continue
            timestamp = datetime.fromisoformat(value)
            if timestamp.tzinfo is not None:
                timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
            rows.append({"ticket_id": ticket_id, "last_staff_activity_at": timestamp})
        if rows:
            statement = insert(TicketStaffActivity)
            await self.session.execute(statement.on_conflict_do_update(
                index_elements=["ticket_id"],
                set_={"last_staff_activity_at": func.max(
                    TicketStaffActivity.last_staff_activity_at, statement.excluded.last_staff_activity_at,
                )},
            ), rows)
            await self.session.commit()
