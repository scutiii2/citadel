"""Games gain a wallpaper URL taken from their manifest."""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("games") as batch:
        batch.add_column(sa.Column("wallpaper", sa.String(1000), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("games") as batch:
        batch.drop_column("wallpaper")
