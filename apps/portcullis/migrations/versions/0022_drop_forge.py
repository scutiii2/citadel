"""Remove the retired Forge tables and the forge.use permission grants."""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    for table in ("forge_messages", "forge_group_workers", "forge_groups", "forge_workers"):
        if table in tables:
            op.drop_table(table)
    conn.execute(sa.text(
        "DELETE FROM role_permission WHERE permission_id IN "
        "(SELECT id FROM permissions WHERE name = 'forge.use')"
    ))
    conn.execute(sa.text("DELETE FROM permissions WHERE name = 'forge.use'"))
    conn.execute(sa.text("DELETE FROM app_settings WHERE name IN ('forge_plans_claude', 'forge_plans_codex')"))


def downgrade():
    # Intentionally irreversible: deleted workers, groups and messages cannot be restored.
    pass
