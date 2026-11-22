"""Rename extensions.manage to tool_services.manage: shared extensions are gone, tool services remain."""

from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

_OLD, _NEW = "extensions.manage", "tool_services.manage"
_OLD_ROLE_TEXT = "Member access plus shared extension management."
_NEW_ROLE_TEXT = "Member access plus tool services management."
_OLD_DESCRIPTION = "Add and remove mcp_server extensions (other MCP servers offered to every client)"
_DESCRIPTION = "Add, test and remove the Bard, Scribe and Reader connections in Stronghold Admin"


def _rename(old: str, new: str, description: str) -> None:
    conn = op.get_bind()
    if conn.execute(sa.text("SELECT 1 FROM permissions WHERE name = :new"), {"new": new}).first():
        # Both rows exist (a rewound database): fold the old grants into the new row, then drop the old row.
        conn.execute(sa.text(
            "INSERT INTO role_permission (role_id, permission_id) "
            "SELECT rp.role_id, (SELECT id FROM permissions WHERE name = :new) FROM role_permission rp "
            "JOIN permissions p ON p.id = rp.permission_id WHERE p.name = :old AND NOT EXISTS ("
            "SELECT 1 FROM role_permission x WHERE x.role_id = rp.role_id "
            "AND x.permission_id = (SELECT id FROM permissions WHERE name = :new))"
        ), {"old": old, "new": new})
        conn.execute(sa.text("DELETE FROM role_permission WHERE permission_id IN (SELECT id FROM permissions WHERE name = :old)"), {"old": old})
        conn.execute(sa.text("DELETE FROM permissions WHERE name = :old"), {"old": old})
    conn.execute(sa.text("UPDATE permissions SET name = :new WHERE name = :old"), {"old": old, "new": new})
    conn.execute(sa.text("UPDATE permissions SET description = :d WHERE name = :new"), {"d": description, "new": new})


def _role_text(old: str, new: str) -> None:
    op.get_bind().execute(
        sa.text("UPDATE roles SET description = :new WHERE name = 'Power User' AND description = :old"),
        {"new": new, "old": old},
    )


def upgrade() -> None:
    _rename(_OLD, _NEW, _DESCRIPTION)
    _role_text(_OLD_ROLE_TEXT, _NEW_ROLE_TEXT)


def downgrade() -> None:
    _rename(_NEW, _OLD, _OLD_DESCRIPTION)
    _role_text(_NEW_ROLE_TEXT, _OLD_ROLE_TEXT)
