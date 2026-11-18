"""Seed six starter roles, once: Viewer, Support, Moderator, Auditor, Power User, Operator.

A role whose name already exists is left untouched, so admin edits and
deletions stick: re-running never restores a removed grant or role.
Permission rows are created when missing; the application registry fills in
their descriptions at startup.
"""

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

# Frozen migration data: never import the application's evolving registry.
_MEMBER = [
    "chat.use", "chat.share", "tools.view", "tools.execute",
    "extensions.personal.manage", "files.upload", "files.download", "tickets.create",
]
ROLES = {
    "Viewer": ("Chat only: no tool runs, uploads or sharing.", ["chat.use", "tools.view"]),
    "Support": (
        "Triage tickets and see account, error and traffic status.",
        ["tickets.create", "tickets.manage", "accounts.view", "logs.errors.view", "traffic.view"],
    ),
    "Moderator": (
        "Manage accounts and invites. Cannot delete accounts or change roles.",
        ["accounts.view", "accounts.manage", "invites.manage", "logs.view", "logs.errors.view"],
    ),
    "Auditor": (
        "Read-only oversight of accounts, roles, usage, logs and traffic.",
        ["accounts.view", "roles.view", "usage.all.view", "logs.view", "logs.errors.view",
         "config.issues.view", "traffic.view"],
    ),
    "Power User": ("Member access plus shared extension management.", _MEMBER + ["extensions.manage"]),
    "Operator": (
        "Run the platform: settings, capabilities and extensions. No account or role control.",
        ["capabilities.manage", "settings.manage", "extensions.manage", "config.issues.view"],
    ),
}


def upgrade():
    conn = op.get_bind()
    for name, (description, permissions) in ROLES.items():
        exists = conn.execute(sa.text("SELECT 1 FROM roles WHERE name = :n"), {"n": name}).first()
        if exists:
            continue
        conn.execute(sa.text("INSERT INTO roles (name, description) VALUES (:n, :d)"),
                     {"n": name, "d": description})
        for permission in permissions:
            conn.execute(sa.text(
                "INSERT INTO permissions (name, description) SELECT :p, NULL "
                "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = :p)"
            ), {"p": permission})
            conn.execute(sa.text(
                "INSERT INTO role_permission (role_id, permission_id) "
                "SELECT r.id, p.id FROM roles r, permissions p WHERE r.name = :n AND p.name = :p"
            ), {"n": name, "p": permission})


def downgrade():
    conn = op.get_bind()
    for name in ROLES:
        conn.execute(sa.text(
            "DELETE FROM role_permission WHERE role_id IN (SELECT id FROM roles WHERE name = :n)"
        ), {"n": name})
        conn.execute(sa.text("DELETE FROM account_role WHERE role_id IN (SELECT id FROM roles WHERE name = :n)"),
                     {"n": name})
        conn.execute(sa.text("DELETE FROM roles WHERE name = :n"), {"n": name})
