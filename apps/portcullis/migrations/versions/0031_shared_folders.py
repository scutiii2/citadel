"""Temporary shared folders: two tables, and the new `folders.use` permission for every role that can share chat links, once.

Later revocations stick: re-running startup never restores a revoked grant."""

from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

# Frozen migration data: never import the application's evolving registry.
SOURCE = "chat.share"
TARGET = "folders.use"


def upgrade() -> None:
    op.create_table(
        "shared_folders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_shared_folders_account_id", "shared_folders", ["account_id"])
    op.create_index("ix_shared_folders_expires_at", "shared_folders", ["expires_at"])
    op.create_table(
        "shared_folder_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("folder_id", sa.Integer(), sa.ForeignKey("shared_folders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_shared_folder_files_folder_id", "shared_folder_files", ["folder_id"])

    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO permissions (name, description) SELECT :name, NULL "
        "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = :name)"
    ), {"name": TARGET})
    conn.execute(sa.text(
        "INSERT INTO role_permission (role_id, permission_id) "
        "SELECT old.role_id, new.id FROM role_permission old "
        "JOIN permissions legacy ON legacy.id = old.permission_id "
        "JOIN permissions new ON new.name = :target "
        "WHERE legacy.name = :source AND NOT EXISTS "
        "(SELECT 1 FROM role_permission present WHERE present.role_id = old.role_id "
        "AND present.permission_id = new.id)"
    ), {"source": SOURCE, "target": TARGET})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM role_permission WHERE permission_id IN (SELECT id FROM permissions WHERE name = :name)"
    ), {"name": TARGET})
    conn.execute(sa.text("DELETE FROM permissions WHERE name = :name"), {"name": TARGET})
    op.drop_table("shared_folder_files")
    op.drop_table("shared_folders")
