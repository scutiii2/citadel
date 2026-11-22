# Plan 27: Final leftovers (Armory table prune, starter role names, Plan 14 closed) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Run the three tasks straight through in the current checkout and report once at the end. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Close the three optional items that were left after Plans 22c to 22e. (1) A small, safe script removes the unused `extensions` and `connections` tables from Armory's `settings.db`. (2) The two starter roles whose names or text still talk about shared extensions are renamed or reworded. (3) The roadmap and docs say that Plan 14 is fully reversed, so nothing is "remaining".

**Architecture:** No runtime behaviour changes. Task 1 is an explicit, dry-run-by-default command an operator runs once; Armory itself never drops tables at startup. Task 2 is one reversible Portcullis migration that changes data only where the text is still the seeded text. Task 3 is text.

**Tech Stack:** Python 3.11+ (Armory, Portcullis, Alembic), `uv`, pytest.

**Spec:** [2026-11-20-service-scopes-design.md](../specs/2026-11-20-service-scopes-design.md). Follows [Plan 22c](2026-11-22-plan-22c-remove-extension-proxy.md) (its open question 2) and [Plan 22e](2026-11-22-plan-22e-rename-extensions-manage.md) (its "Out of scope"). Roadmap row 27.

## Global Constraints

- Delete no data other than the two named tables of `settings.db`, and only when an operator runs the script with `--apply`. Never touch the tables `environment`, `email`, `tuning`, `settings` or any other table, and never any other database file.
- Armory does not run the prune itself and gains no startup code.
- Roles are data an administrator may have edited. The migration changes a role only when its name and description are exactly the seeded values; any other role is left alone. No account's role assignment changes (assignments point at the role id).
- Old migrations (`0010`, `0019`, `0029`) are not edited.
- Keep: `apps/ember_web` (reference only, never edited), old plan and spec files.
- Never read, print or write `.env*`, `secrets/` or key files. Never open a real `settings.db`: tests use a temporary database. No reduced-motion code (repo rule). Use `uv`. Keep each file's line endings; edit with editor tools.
- Work in the current checkout and branch. Do not create a branch, worktree or commit unless the user asks. Do not push.
- Test budget: each task runs only the files it names, once, with the command it gives. No full suites, no Docker. Python: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider <files>` from the app folder (if it fails, use the app's `.venv\Scripts\python.exe -u -m pytest ...`). A run over about 2 minutes: stop and say so.

## What the checks found (2026-11-22, on `main` `84a46790`)

| Item | State |
|---|---|
| Armory `settings.db` tables `extensions` and `connections` | Created lazily by `citadel_auth/settings_store.py` (`CREATE TABLE IF NOT EXISTS`, key + JSON value). After Plan 22c nothing in Armory reads or writes them. Armory has no `tools/` folder and no prune code |
| Starter roles (`0019_starter_roles.py`) | `Power User`: "Member access plus shared extension management." (after `0029`: "Member access plus tool services management."), grants Member permissions plus the renamed `tool_services.manage`. `Operator`: "Run the platform: settings, capabilities and extensions. No account or role control." |
| Plan 14 | Built 2026-11-18, then reversed by Plans 19 (Stronghold owns tool services), 22 (façade, dictation) and 22c (connection store code, Connections page). Roadmap rows 19 and 22c still carry a "Plan 14 remains" cell; the only thing left of it is the two Armory tables of Task 1 |

---

### Task 1: Armory prune script

**Files:**
- Create: `apps/armory/src/prune_unused_tables.py`
- Create: `apps/armory/tests/test_prune_unused_tables.py`
- Modify: `apps/armory/README.md` (one short "Maintenance" paragraph)

- [ ] **Step 1: Write the failing test**

```python
"""prune_unused_tables: drops only the two dead tables, only with --apply."""

import sqlite3

from src import prune_unused_tables


def _make(path):
    with sqlite3.connect(path) as db:
        for name in ("extensions", "connections", "environment", "email", "tuning", "settings"):
            db.execute(f"CREATE TABLE {name} (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute(f"INSERT INTO {name} VALUES ('k', '{{}}')")


def _tables(path):
    with sqlite3.connect(path) as db:
        return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_dry_run_changes_nothing_and_reports_the_tables(tmp_path, capsys):
    path = tmp_path / "settings.db"
    _make(path)
    assert prune_unused_tables.main([str(path)]) == 0
    assert {"extensions", "connections"} <= _tables(path)
    assert "extensions" in capsys.readouterr().out


def test_apply_drops_only_the_two_dead_tables(tmp_path):
    path = tmp_path / "settings.db"
    _make(path)
    assert prune_unused_tables.main([str(path), "--apply"]) == 0
    assert _tables(path) == {"environment", "email", "tuning", "settings"}
    assert prune_unused_tables.main([str(path), "--apply"]) == 0  # again: nothing left, no error


def test_a_missing_file_is_an_error_and_is_not_created(tmp_path):
    path = tmp_path / "absent.db"
    assert prune_unused_tables.main([str(path), "--apply"]) == 1
    assert not path.exists()
```

- [ ] **Step 2: Run it and see it fail**

From `apps/armory`: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_prune_unused_tables.py`. Expect: `ModuleNotFoundError` for `src.prune_unused_tables`.

- [ ] **Step 3: Write the script**

```python
"""One-off maintenance: remove the unused `extensions` and `connections` tables from Armory's settings.db.

Plans 14 to 22c moved shared extensions and tool connections out of Armory; nothing reads these tables any more.
Dry run by default. Run `python -m src.prune_unused_tables <path to settings.db> --apply` while Armory is stopped,
after copying the file. Only these two tables are touched."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

DEAD_TABLES = ("extensions", "connections")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("database", type=Path, help="path to settings.db")
    parser.add_argument("--apply", action="store_true", help="drop the tables (default: only report)")
    args = parser.parse_args(argv)
    if not args.database.is_file():
        print(f"No such file: {args.database}", file=sys.stderr)
        return 1
    with closing(sqlite3.connect(args.database, timeout=10)) as db, db:
        for table in DEAD_TABLES:
            present = db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
            if not present:
                print(f"{table}: not present")
                continue
            rows = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if args.apply:
                db.execute(f"DROP TABLE {table}")
                print(f"{table}: dropped ({rows} rows)")
            else:
                print(f"{table}: would drop ({rows} rows); run again with --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

The table names come from the constant above, never from input, so the f-strings are safe.

- [ ] **Step 4: Run it and see it pass**

Same command as step 2. Expected: 3 passed.

- [ ] **Step 5: Document**

Add to `apps/armory/README.md` a short "Maintenance" paragraph: the command above, that it is dry-run by default, that Armory must be stopped, that the file should be copied first, and that only `extensions` and `connections` are removed.

---

### Task 2: Starter role names and text

**Files:**
- Create: `apps/portcullis/migrations/versions/0030_rename_starter_roles.py`
- Modify tests: `apps/portcullis/tests/test_migrations.py` (`HEAD = "0030"`, `NEXT = "0031"`, one new test)
- Modify: `apps/portcullis/README.md` if it names the roles

Decision made here, change it before building if you disagree: `Power User` becomes `Tool Services Manager`, because after Plan 22e it is Member access plus `tool_services.manage` only. `Operator` keeps its name and gets text without "extensions".

- [ ] **Step 1: Write the failing test**

In `test_migrations.py` add a test beside the one for `0029` (read it for the helpers; build a database at `0029`, upgrade one step, read back):

```python
def test_0030_renames_the_seeded_power_user_role_only_when_unedited(tmp_path):
    # Database at 0029 with: a role "Power User" holding the 0029 text; a role "Operator" holding the 0019 text.
    ...
    assert roles["Tool Services Manager"].description == "Member access plus tool services management."
    assert "Power User" not in roles
    assert roles["Operator"].description == "Run the platform: settings, capabilities and tool services. No account or role control."
    # The same accounts still hold the renamed role, and its permissions are unchanged.
    # downgrade restores both names and texts.
```

Add a second test with a `Power User` role whose description an administrator edited, and a third with a role already named `Tool Services Manager`; in both the migration leaves `Power User` unchanged and raises no error. The contract: a rename needs the exact seeded name and description and a free target name; the role id, permissions and holders never change; the downgrade reverses what the upgrade did.

- [ ] **Step 2: Run it and see it fail**

From `apps/portcullis`: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_migrations.py -k "0030"`. Expect: no revision `0030`.

- [ ] **Step 3: Migration**

`0030_rename_starter_roles.py`, `revision = "0030"`, `down_revision = "0029"`. Use the same `sa.text` style as `0029`:

```python
_OLD_NAME, _NEW_NAME = "Power User", "Tool Services Manager"
_POWER_TEXT = "Member access plus tool services management."
_OPERATOR_OLD = "Run the platform: settings, capabilities and extensions. No account or role control."
_OPERATOR_NEW = "Run the platform: settings, capabilities and tool services. No account or role control."


def _rename_role(old: str, new: str, text: str) -> None:
    conn = op.get_bind()
    taken = conn.execute(sa.text("SELECT 1 FROM roles WHERE name = :new"), {"new": new}).first()
    if not taken:
        conn.execute(sa.text("UPDATE roles SET name = :new WHERE name = :old AND description = :text"),
                     {"new": new, "old": old, "text": text})


def _operator_text(old: str, new: str) -> None:
    op.get_bind().execute(sa.text("UPDATE roles SET description = :new WHERE name = 'Operator' AND description = :old"),
                          {"new": new, "old": old})


def upgrade() -> None:
    _rename_role(_OLD_NAME, _NEW_NAME, _POWER_TEXT)
    _operator_text(_OPERATOR_OLD, _OPERATOR_NEW)


def downgrade() -> None:
    _rename_role(_NEW_NAME, _OLD_NAME, _POWER_TEXT)
    _operator_text(_OPERATOR_NEW, _OPERATOR_OLD)
```

Check the real table and column names against `0019` and `src/models/role.py`, and whether role names are unique. Check that `src` never looks a role up by the name `Power User` or `Operator`: `git grep -n "Power User" -- apps` (code, not migrations or tests) must be empty, or the code is updated and listed under Findings.

- [ ] **Step 4: Run the tests**

From `apps/portcullis`: `uv run --no-sync python -u -m pytest -q -p no:cacheprovider tests/test_migrations.py`. Expected: all pass (the test at line ~758 reads the starter roles by name from a database built to `0019`; fix it only if it runs to head).

---

### Task 3: Close Plan 14 in the roadmap and docs

**Files:**
- Modify: `docs/superpowers/plans/2026-11-20-scope-roadmap.md`

The roadmap is the only file this task edits; it is no longer held by another session. No tests.

- [ ] **Step 1:** In the roadmap, remove the "Plan 14" cell text ("Plan 14", "Plan 14 remains") from the "what remains" column of rows 19 and 22c, leaving `none`. Row 27 (this plan) already exists; change its label from Written to Built.

- [ ] **Step 2:** `git grep -n "Plan 14 remains" -- docs apps` returns nothing.

---

## Report

Report once: per task what changed (files), the test commands run with pass counts, the commands not run, "Findings" (any role lookup by name found in code, any starter role text that differed), anything not verified, and the vault notes that need an update (Armory, Portcullis, Citadel). Say plainly that the prune script was never run against a real `settings.db`, and that the operator step is: stop Armory, copy `settings.db`, run the dry run, then `--apply`.
