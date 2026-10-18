"""Forge: a user's workers (the Claude and Codex CLIs on their own computer) and their group chats."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base, utcnow


class ForgeWorker(Base):
    """One paired worker. `label` is its @mention handle (lower case, unique per
    account). Only the SHA-256 of the pairing token is kept. Deleting the row
    revokes the worker: its group memberships go with it (foreign key cascade)."""

    __tablename__ = "forge_workers"
    __table_args__ = (UniqueConstraint("account_id", "label"), UniqueConstraint("token_hash"))

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(24))
    token_hash: Mapped[str] = mapped_column(String(64))
    # The plan the worker said its CLI is logged in with; Ember does not verify it.
    reported_plan: Mapped[str | None] = mapped_column(String(80), default=None)
    last_seen: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ForgeGroup(Base):
    """A group chat: one human (the account) and the workers invited into it."""

    __tablename__ = "forge_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(80))
    # ask | accept_edits | plan | full_auto
    mode: Mapped[str] = mapped_column(String(16), default="ask")
    # A worker may hand a turn to another worker (off by default).
    relay: Mapped[bool] = mapped_column(default=False, server_default=false())
    # The worker the user addressed last; a message with no @mention goes there.
    last_worker_id: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ForgeGroupWorker(Base):
    """A worker invited into a group, with the folder it works in on its own computer."""

    __tablename__ = "forge_group_workers"

    group_id: Mapped[int] = mapped_column(ForeignKey("forge_groups.id", ondelete="CASCADE"), primary_key=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("forge_workers.id", ondelete="CASCADE"), primary_key=True)
    folder: Mapped[str] = mapped_column(String(500))
    # The newest message this worker has been shown (the next turn sends only what came after).
    last_seq: Mapped[int] = mapped_column(default=0)


class ForgeMessage(Base):
    """One transcript entry. `seq` rises by one per group, so a browser resumes from the last one it saw."""

    __tablename__ = "forge_messages"
    __table_args__ = (UniqueConstraint("group_id", "seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("forge_groups.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int]
    # "user", "system", or a worker id as text.
    sender: Mapped[str] = mapped_column(String(16))
    # text | tool | permission_request | permission_result | system
    kind: Mapped[str] = mapped_column(String(24))
    body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
