from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base, utcnow


class OutsideClient(Base):
    """A program outside the Citadel that may call some services with its own key.
    Only the key's sha256 hash and first 8 characters are stored."""

    __tablename__ = "outside_clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    key_prefix: Mapped[str] = mapped_column(String(8))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    services: Mapped[list] = mapped_column(JSON, default=list)
    ip_allow: Mapped[list] = mapped_column(JSON, default=list)
    rate_per_minute: Mapped[int] = mapped_column(default=10)
    budget_tokens: Mapped[int]
    budget_days: Mapped[int] = mapped_column(default=30)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_used_at: Mapped[datetime | None]


class OutsideClientEvent(Base):
    """One call or refusal by an outside client. Never holds question or answer text."""

    __tablename__ = "outside_client_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("outside_clients.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    service: Mapped[str] = mapped_column(String(40))
    # "call" or "refused".
    action: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[int]
    tokens: Mapped[int] = mapped_column(default=0)
    ip: Mapped[str] = mapped_column(String(64), default="")
