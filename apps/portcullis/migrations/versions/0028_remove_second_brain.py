"""Remove chat auto-save to Obsidian and its publishing permission."""

from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

_PERMISSION = "brain.instance.publish"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM role_permission WHERE permission_id IN "
        "(SELECT id FROM permissions WHERE name = :name)"
    ), {"name": _PERMISSION})
    conn.execute(sa.text("DELETE FROM permissions WHERE name = :name"), {"name": _PERMISSION})
    with op.batch_alter_table("chats") as batch:
        batch.drop_column("save_to_second_brain")
        batch.drop_column("second_brain_scope")


def downgrade() -> None:
    with op.batch_alter_table("chats") as batch:
        batch.add_column(sa.Column("save_to_second_brain", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("second_brain_scope", sa.String(16), nullable=False, server_default="instance"))
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO permissions (name, description) VALUES (:name, :description)"
    ), {"name": _PERMISSION, "description": "Publish durable knowledge to the shared Instance Brain"})
    conn.execute(sa.text(
        "INSERT INTO role_permission (role_id, permission_id) "
        "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p "
        "WHERE r.name = 'Administrator' AND p.name = :name"
    ), {"name": _PERMISSION})
