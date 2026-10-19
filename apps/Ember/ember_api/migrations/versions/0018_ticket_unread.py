"""Track staff activity and account read receipts for upstream tickets."""

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ticket_staff_activity",
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("last_staff_activity_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("ticket_id"),
    )
    op.create_table(
        "account_ticket_seen",
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_id", "ticket_id"),
    )


def downgrade():
    op.drop_table("account_ticket_seen")
    op.drop_table("ticket_staff_activity")
