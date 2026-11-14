"""Persist the per-chat second brain auto-save preference, default off."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("save_to_second_brain", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("chats", "save_to_second_brain")
