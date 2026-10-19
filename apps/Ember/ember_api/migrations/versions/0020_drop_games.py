"""Remove the retired game registry, launch tickets and permission grants."""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    for table in ("game_tickets", "games"):
        if table in tables:
            op.drop_table(table)
    predicate = "name = 'games.manage' OR name LIKE 'games.%.play'"
    conn.execute(sa.text(
        "DELETE FROM role_permission WHERE permission_id IN "
        f"(SELECT id FROM permissions WHERE {predicate})"
    ))
    conn.execute(sa.text(f"DELETE FROM permissions WHERE {predicate}"))


def downgrade():
    # Intentionally irreversible: deleted registry data and grants cannot be restored.
    pass
