"""Chat-turn log entries gain a column for the prompts each agent received."""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("log_entries") as batch:
        batch.add_column(sa.Column("prompts", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("log_entries") as batch:
        batch.drop_column("prompts")
