"""Games gain a list of badge images (JSON text) taken from their manifest."""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("games") as batch:
        batch.add_column(sa.Column("symbols", sa.Text(), nullable=False, server_default="[]"))


def downgrade():
    with op.batch_alter_table("games") as batch:
        batch.drop_column("symbols")
