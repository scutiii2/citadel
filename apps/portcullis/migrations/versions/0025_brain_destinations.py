"""Explicit chat publication destinations and shared-brain publishing permission."""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chats", sa.Column("second_brain_scope", sa.String(16), nullable=False, server_default="instance"))
    conn = op.get_bind()
    conn.execute(sa.text("INSERT INTO permissions (name, description) SELECT :name, :description WHERE NOT EXISTS "
                         "(SELECT 1 FROM permissions WHERE name=:name)"),
                 {"name": "brain.instance.publish", "description": "Publish durable knowledge to the shared Instance Brain"})
    conn.execute(sa.text("INSERT INTO role_permission (role_id, permission_id) "
        "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE r.name='Administrator' "
        "AND p.name='brain.instance.publish' AND NOT EXISTS (SELECT 1 FROM role_permission rp WHERE rp.role_id=r.id AND rp.permission_id=p.id)"))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM role_permission WHERE permission_id IN (SELECT id FROM permissions WHERE name='brain.instance.publish')"))
    conn.execute(sa.text("DELETE FROM permissions WHERE name='brain.instance.publish'"))
    op.drop_column("chats", "second_brain_scope")
