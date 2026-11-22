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
