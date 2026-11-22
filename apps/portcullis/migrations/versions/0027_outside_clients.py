"""Outside clients: keyed programs outside the Citadel, and their audit events.

Revision ID: 0027
Revises: 0026
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outside_clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uid", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(60), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(8), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("services", sa.JSON(), nullable=False),
        sa.Column("ip_allow", sa.JSON(), nullable=False),
        sa.Column("rate_per_minute", sa.Integer(), nullable=False),
        sa.Column("budget_tokens", sa.Integer(), nullable=False),
        sa.Column("budget_days", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_outside_clients_key_hash", "outside_clients", ["key_hash"], unique=True)
    op.create_table(
        "outside_client_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("outside_clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("service", sa.String(40), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("ip", sa.String(64), nullable=False),
    )
    op.create_index("ix_outside_client_events_client_id", "outside_client_events", ["client_id"])
    op.create_index("ix_outside_client_events_at", "outside_client_events", ["at"])


def downgrade() -> None:
    op.drop_index("ix_outside_client_events_at", table_name="outside_client_events")
    op.drop_index("ix_outside_client_events_client_id", table_name="outside_client_events")
    op.drop_table("outside_client_events")
    op.drop_index("ix_outside_clients_key_hash", table_name="outside_clients")
    op.drop_table("outside_clients")
