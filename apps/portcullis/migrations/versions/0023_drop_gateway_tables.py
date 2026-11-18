"""Drop the tables whose data now lives in db_gateway.

Nav preferences, account capabilities, prompt templates and private extensions are documents in
db_gateway (collections nav_preferences, account_capabilities, prompt_templates, user_extensions).
The migration refuses to run while any of these tables still holds rows, so nothing is lost: copy
the rows to db_gateway (or empty the tables) first.
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

TABLES = ("nav_preferences", "account_capabilities", "prompt_templates", "user_extensions")


def upgrade():
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    present = [table for table in TABLES if table in existing]
    filled = {
        table: count for table in present
        if (count := bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar())
    }
    if filled:
        rows = ", ".join(f"{table} ({count} rows)" for table, count in filled.items())
        raise RuntimeError(
            f"Migration 0023 would delete data that is not in db_gateway yet: {rows}. "
            "Copy these rows to db_gateway, or empty the tables, then run the migration again."
        )
    for table in present:
        op.drop_table(table)


def downgrade():
    # Intentionally irreversible: the data lives in db_gateway now, not in this database.
    pass
