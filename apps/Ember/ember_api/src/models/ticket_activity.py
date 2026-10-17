"""Local read receipts for tickets owned by the upstream ticket service."""

from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base


class TicketStaffActivity(Base):
    __tablename__ = "ticket_staff_activity"

    ticket_id: Mapped[int] = mapped_column(primary_key=True)
    last_staff_activity_at: Mapped[datetime]


class AccountTicketSeen(Base):
    __tablename__ = "account_ticket_seen"

    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(primary_key=True)
    last_seen_at: Mapped[datetime]
