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
