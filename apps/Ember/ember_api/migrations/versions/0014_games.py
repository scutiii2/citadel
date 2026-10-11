"""Game registry, hashed launch tickets, and the per-game permission rename."""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None
OLD = "ascension.play"
NEW = "games.ascension.play"


def _rename(source: str, target: str) -> None:
    conn = op.get_bind()
    has_target = conn.execute(sa.text("SELECT 1 FROM permissions WHERE name = :name"), {"name": target}).first()
    if not has_target:
        conn.execute(sa.text("UPDATE permissions SET name = :target WHERE name = :source"), {"source": source, "target": target})
        return
    conn.execute(sa.text(
        "INSERT INTO role_permission (role_id, permission_id) "
        "SELECT old.role_id, new.id FROM role_permission old "
        "JOIN permissions legacy ON legacy.id = old.permission_id "
        "JOIN permissions new ON new.name = :target "
        "WHERE legacy.name = :source AND NOT EXISTS "
        "(SELECT 1 FROM role_permission present WHERE present.role_id = old.role_id "
        "AND present.permission_id = new.id)"
    ), {"source": source, "target": target})
    conn.execute(sa.text(
        "DELETE FROM role_permission WHERE permission_id IN (SELECT id FROM permissions WHERE name = :source)"
    ), {"source": source})
    conn.execute(sa.text("DELETE FROM permissions WHERE name = :source"), {"source": source})


def upgrade():
    op.create_table("games",
        sa.Column("id", sa.String(63), primary_key=True),
        sa.Column("url", sa.String(1000), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("icon", sa.String(300), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("manifest", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False))
    op.create_table("game_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("game_id", sa.String(63), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True))
    op.create_index("ix_game_tickets_game_id", "game_tickets", ["game_id"])
    op.create_index("ix_game_tickets_expires_at", "game_tickets", ["expires_at"])
    _rename(OLD, NEW)


def downgrade():
    _rename(NEW, OLD)
    op.drop_table("game_tickets")
    op.drop_table("games")
