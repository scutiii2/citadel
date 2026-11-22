# Plan 22e: Rename the permission `extensions.manage` to `tool_services.manage` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Run the two tasks straight through in the current checkout and report once at the end. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The permission that says "Add and remove mcp_server extensions (other MCP servers offered to every client)" no longer describes anything. Shared extensions are gone (Plans 22c, 22d). The permission still guards one thing: Portcullis's `/api/admin/tool-services` routes (Bard, Scribe and Reader connections in Stronghold Admin). Rename it to `tool_services.manage` with a description that says so. Every role that holds the old name keeps the new one.

**Architecture:** One reversible Portcullis migration renames the `permissions` row in place (the role grants point at the row id, so they follow). The constant, description and the one route guard change with it; three front ends change the name they check. `extensions.personal.manage` is a different, live permission (private extensions) and does not change.

**Tech Stack:** Python 3.11+ (Portcullis, Alembic), Vue 3 + TypeScript (Portcullis Admin, Stronghold Admin, Armory Admin, Ember), `uv`, `pnpm`, pytest, vitest.

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md). Follows [Plan 22c](2026-11-22-plan-22c-remove-extension-proxy.md) and [Plan 22d](2026-11-22-plan-22d-remove-extension-plumbing.md). Roadmap row 22e.

## Global Constraints

- Rename only `extensions.manage`. Do not touch `extensions.personal.manage`, `private_extensions`, `/api/user-extensions` or Stronghold's `/extensions` routes.
- No role is changed except through the rename. No account, route or screen is added. No dependency.
- Old migrations (`0010`, `0019`) keep the old name: they describe what the database was then. Do not edit them.
- Portcullis's startup creates a missing known permission and refreshes known descriptions. After this plan it creates `tool_services.manage` if absent. An old `extensions.manage` row left behind is treated like any retired permission and is not touched by startup.
- Keep: `apps/ember_web` (reference only, never edited), old plan and spec files.
- Never read, print or write `.env*`, `secrets/` or key files. No reduced-motion code (repo rule). Use `uv` and `pnpm`. Keep each file's line endings; edit with editor tools.
- Work in the current checkout and branch. Do not create a branch, worktree or commit unless the user asks. Do not push.
- Test budget: each task runs only the files it names, once, with the command it gives. No full suites, no Docker. Python: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider <files>` from the app folder (if it fails, use the app's `.venv\Scripts\python.exe -u -m pytest ...`). Front ends: `pnpm exec vitest run <files>` from the app folder. A run over about 2 minutes: stop and say so.

## What the checks found (2026-11-22, on `main` `e2758ad4`)

| Place | Use |
|---|---|
| `apps/portcullis/src/services/permissions.py` lines 23, 55, 72 | constant `EXTENSIONS_MANAGE`, its description, and the staff list (verified email needed) |
| `apps/portcullis/src/routes/connections.py` lines 11, 15 | `manage = require_permission(EXTENSIONS_MANAGE)` on the five `/admin/tool-services` routes; the only guard that uses it |
| `apps/portcullis/migrations/versions/0019_starter_roles.py` | grants it to Administrator, the Power User role ("Member access plus shared extension management.") and Operator; stays as history |
| `apps/portcullis/tests/test_migrations.py` lines 20, 21, 758; `test_admin.py` 344 to 347; `test_auth.py` 130, 139 | `HEAD = "0028"`, `NEXT = "0029"`, and the name in three assertions |
| `apps/portcullis_admin/src/components/admin/RoleEditor.vue` lines 63, 72; `e2e/fakeApi.ts` line 13; `e2e/workspaceFakeApi.ts` line 48 | label "Manage shared extensions", the "Workspace & monitoring" group, fake data |
| `apps/stronghold_admin/src/router/index.ts` line 24; `src/router/pages.ts` line 52; `src/api/ToolServicesClient.ts` line 33 (comment) | gate the Tool services page |
| `apps/ember/src/utils/navigation/adminLink.ts` line 4 | `ADMIN_ACCESS_PERMISSIONS` |
| `apps/armory_admin/src/views/NoAccessView.vue` line 11; `src/components/IntegrationToolsModal.test.ts` lines 16, 54 | Armory Admin gates only on `capabilities.manage` now; the text and the test data still name `extensions.manage` |

---

### Task 1: Portcullis renames the permission

**Files:**
- Create: `apps/portcullis/migrations/versions/0029_rename_extensions_manage.py`
- Modify: `apps/portcullis/src/services/permissions.py`, `apps/portcullis/src/routes/connections.py`
- Modify tests: `apps/portcullis/tests/test_migrations.py`, `test_admin.py`, `test_auth.py`
- Read, update only if it names the permission: `apps/portcullis/tests/test_tool_services_admin.py`, `test_config_issues.py`, `apps/portcullis/README.md`

- [ ] **Step 1: Write the failing tests**

In `test_migrations.py` set `HEAD = "0029"` and `NEXT = "0030"`. Add a test next to the one for `0028` (read it for the helpers; use the same way of building a database at revision `0028` and upgrading one step):

```python
def test_0029_renames_extensions_manage_and_keeps_every_role_grant(tmp_path):
    # Build a database at 0028 with a role that holds "extensions.manage", upgrade to 0029,
    # then read the permissions and grants back.
    ...
    assert names == {"tool_services.manage"} and "extensions.manage" not in names
    assert holders_of("tool_services.manage") == holders_before  # same roles, same count
    # downgrade restores the old name and the same holders
```

Write the body with the file's own helpers; the three assertions above are the contract: the new name exists, the old name is gone, the same roles hold it, and the downgrade restores the old name. Also assert that a role named `Power User` whose description is the old text `Member access plus shared extension management.` gets `Member access plus tool services management.`, and a role with any other description keeps it.

In `test_admin.py` (`test_extensions_permission_bootstrap_and_descriptions`) and `test_auth.py` (the restart test) replace `extensions.manage` with `tool_services.manage` and the expected description with `Add, test and remove the Bard, Scribe and Reader connections in Stronghold Admin`.

- [ ] **Step 2: Run them and see them fail**

From `apps/portcullis`: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_migrations.py tests/test_admin.py tests/test_auth.py -k "0029 or extensions_permission or permission_descriptions"`. Expect: no revision `0029`, and the old name still returned.

- [ ] **Step 3: Migration**

`0029_rename_extensions_manage.py`, with `revision = "0029"`, `down_revision = "0028"`:

```python
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
_DESCRIPTION = "Add, test and remove the Bard, Scribe and Reader connections in Stronghold Admin"


def _rename(old: str, new: str, description: str | None) -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE permissions SET name = :new WHERE name = :old"), {"old": old, "new": new})
    if description is not None:
        conn.execute(sa.text("UPDATE permissions SET description = :d WHERE name = :new"), {"d": description, "new": new})


def upgrade() -> None:
    _rename(_OLD, _NEW, _DESCRIPTION)
    op.get_bind().execute(
        sa.text("UPDATE roles SET description = :new WHERE name = 'Power User' AND description = :old"),
        {"new": _NEW_ROLE_TEXT, "old": _OLD_ROLE_TEXT},
    )


def downgrade() -> None:
    _rename(_NEW, _OLD, "Add and remove mcp_server extensions (other MCP servers offered to every client)")
    op.get_bind().execute(
        sa.text("UPDATE roles SET description = :old WHERE name = 'Power User' AND description = :new"),
        {"new": _NEW_ROLE_TEXT, "old": _OLD_ROLE_TEXT},
    )
```

Check the `roles` table and column names against `src/models/role.py` and `0028` (`role_permission`, `permissions`); fix the SQL if a name differs. A database that has no `extensions.manage` row (a fresh one built from models after this plan) must upgrade cleanly: the `UPDATE` matches nothing.

- [ ] **Step 4: Constant, description, guard**

In `permissions.py` rename `EXTENSIONS_MANAGE = "extensions.manage"` to `TOOL_SERVICES_MANAGE = "tool_services.manage"`, set its description in the descriptions map to the `_DESCRIPTION` text above, and change the name in the staff list (line ~72). In `routes/connections.py` import and use `TOOL_SERVICES_MANAGE`. Run `git grep -n "EXTENSIONS_MANAGE" -- apps/portcullis` and fix every remaining hit. Update `README.md` and `test_tool_services_admin.py` / `test_config_issues.py` only where they name the old permission.

- [ ] **Step 5: Run the tests**

From `apps/portcullis`: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_migrations.py tests/test_admin.py tests/test_auth.py tests/test_tool_services_admin.py tests/test_config_issues.py`. Expected: all pass, except the two known failures if they live in these files (`test_secret_box.py` and `test_traffic.py` are not among them). If a run takes over 2 minutes, stop it and say so.

---

### Task 2: Front ends check the new name

**Files:**
- Modify: `apps/portcullis_admin/src/components/admin/RoleEditor.vue`, `apps/portcullis_admin/e2e/fakeApi.ts`, `apps/portcullis_admin/e2e/workspaceFakeApi.ts`
- Modify: `apps/stronghold_admin/src/router/index.ts`, `src/router/pages.ts`, `src/api/ToolServicesClient.ts` (comment)
- Modify: `apps/ember/src/utils/navigation/adminLink.ts`
- Modify: `apps/armory_admin/src/views/NoAccessView.vue`, `src/components/IntegrationToolsModal.test.ts`
- Test: one assertion in `apps/stronghold_admin/src/router/pages.test.ts` (create the file's test only if the folder already has such a test; otherwise add it to the nearest router test)

- [ ] **Step 1: Write the failing assertion**

In the Stronghold Admin router test, assert that the Tool services page needs the new permission:

```ts
it("gates Tool services on tool_services.manage", () => {
  const page = pages.find((entry) => entry.label === "Tool services");
  expect(page?.permission).toBe("tool_services.manage");
});
```

Use the real export name from `pages.ts`.

- [ ] **Step 2: Run it and see it fail**

From `apps/stronghold_admin`: `pnpm exec vitest run src/router`. Expect: the permission is still `extensions.manage`.

- [ ] **Step 3: Rename in the front ends**

- Stronghold Admin: the two `permission` values and the comment in `ToolServicesClient.ts`.
- Portcullis Admin `RoleEditor.vue`: key `"extensions.manage"` becomes `"tool_services.manage"` with the label `"Manage tool services"` (line 63) and in the group names list (line 72). Update both `e2e` fake files: the permission list entry and its description (`workspaceFakeApi.ts` line 48 uses the new description from Task 1).
- Ember `adminLink.ts`: `ADMIN_ACCESS_PERMISSIONS` uses `"tool_services.manage"`.
- Armory Admin: `NoAccessView.vue` subtitle says only `capabilities.manage` (Armory Admin's pages check nothing else); `IntegrationToolsModal.test.ts` uses `capabilities.manage` in place of `extensions.manage`, then read the test to confirm it still means what it says.

Run `git grep -n "extensions\.manage" -- apps ':!apps/ember_web' ':!apps/portcullis/migrations'` and fix any remaining hit.

- [ ] **Step 4: Run the tests**

```
cd apps/stronghold_admin; pnpm exec vitest run src/router
cd apps/portcullis_admin; pnpm exec vitest run src/components/admin
cd apps/ember; pnpm exec vitest run src/utils/navigation
cd apps/armory_admin; pnpm exec vitest run src/components/IntegrationToolsModal.test.ts
```

Expected: all pass. Do not run Playwright e2e.

---

## Out of scope

- The `Power User` role itself (now only Member plus tool services management). Whether it still earns its place is a product decision.
- A prune script for Armory's unused `extensions` and `connections` tables.
- `extensions.personal.manage`, which gates private extensions and stays.

## Deploy note

Front ends and Portcullis must ship together: an old front end checks `extensions.manage`, which no account holds after the migration, so delegated administrators lose the Tool services link until the front ends update.

## Report

Report once: per task what changed (files), the test commands run with pass counts, the commands not run, anything the final `git grep` still finds with the reason, anything not verified, and the vault notes that need an update (Portcullis, Stronghold Admin, Armory Admin, Ember).
