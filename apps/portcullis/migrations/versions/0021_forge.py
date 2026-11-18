"""Forge: workers, group chats, members and messages.

Revision ID: 0021
Revises: 0020
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forge_workers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("label", sa.String(24), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("reported_plan", sa.String(80), nullable=True),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("account_id", "label"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_forge_workers_account_id", "forge_workers", ["account_id"])
    op.create_table(
        "forge_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("relay", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_worker_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_forge_groups_account_id", "forge_groups", ["account_id"])
    op.create_table(
        "forge_group_workers",
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("forge_groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("worker_id", sa.Integer(), sa.ForeignKey("forge_workers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("folder", sa.String(500), nullable=False),
        sa.Column("last_seq", sa.Integer(), nullable=False),
    )
    op.create_table(
        "forge_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("forge_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("sender", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("group_id", "seq"),
    )
    op.create_index("ix_forge_messages_group_id", "forge_messages", ["group_id"])


def downgrade() -> None:
    # 0022 drops these tables, so they may already be gone; SQLite removes their indexes with them.
    for table in ("forge_messages", "forge_group_workers", "forge_groups", "forge_workers"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
