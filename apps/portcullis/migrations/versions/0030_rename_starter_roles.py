"""Rename the starter role Power User to Tool Services Manager and drop "extensions" from the Operator text.

Only the seeded name and text are changed; an edited role is left alone, and the role id, permissions and holders never change."""

from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_OLD_NAME, _NEW_NAME = "Power User", "Tool Services Manager"
_POWER_TEXT = "Member access plus tool services management."
_OPERATOR_OLD = "Run the platform: settings, capabilities and extensions. No account or role control."
_OPERATOR_NEW = "Run the platform: settings, capabilities and tool services. No account or role control."


def _rename_role(old: str, new: str, text: str) -> None:
    conn = op.get_bind()
    taken = conn.execute(sa.text("SELECT 1 FROM roles WHERE name = :new"), {"new": new}).first()
    if not taken:
        conn.execute(
            sa.text("UPDATE roles SET name = :new WHERE name = :old AND description = :text"),
            {"new": new, "old": old, "text": text},
        )


def _operator_text(old: str, new: str) -> None:
    op.get_bind().execute(
        sa.text("UPDATE roles SET description = :new WHERE name = 'Operator' AND description = :old"),
        {"new": new, "old": old},
    )


def upgrade() -> None:
    _rename_role(_OLD_NAME, _NEW_NAME, _POWER_TEXT)
    _operator_text(_OPERATOR_OLD, _OPERATOR_NEW)


def downgrade() -> None:
    _rename_role(_NEW_NAME, _OLD_NAME, _POWER_TEXT)
    _operator_text(_OPERATOR_NEW, _OPERATOR_OLD)
