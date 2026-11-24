"""Daily counters in Legion's own `stats.db`: tokens used per user and per agent (for budgets) and how often each
routing, confidentiality and batching event happened (for the Insights page).

A counter is one row `<UTC date>|<name>`; adding is one atomic SQL upsert, so agent processes never lose a count.
The file is separate from settings.db on purpose: it changes on every turn, and settings.db changes make every agent
reload its tuning. A failure to write never stops a turn. Rows older than `KEEP_DAYS` are dropped as new days start.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
import re
from pathlib import Path

from src.citadel_auth import data_dir

_log = logging.getLogger(__name__)
DB = data_dir(Path(__file__).resolve().parents[2]) / "stats.db"
KEEP_DAYS = 35


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute("CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
    return connection


def add(name: str, amount: int = 1, path: Path | None = None) -> None:
    """Add `amount` to today's counter `name`. Best effort."""
    if amount <= 0:
        return
    try:
        today = _today()
        with closing(_connect(path or DB)) as connection, connection:
            connection.execute(
                "INSERT INTO counters (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = value + excluded.value",
                (f"{today}|{name}", amount))
            cutoff = (datetime.now(timezone.utc).date() - timedelta(days=KEEP_DAYS)).isoformat()
            connection.execute("DELETE FROM counters WHERE key < ?", (cutoff,))
    except (OSError, sqlite3.Error):
        _log.debug("could not count %s", name, exc_info=True)


def today(name: str, path: Path | None = None) -> int:
    """Today's value of counter `name`; 0 when there is none or the file cannot be read."""
    target = path or DB
    if not target.exists():
        return 0
    try:
        with closing(_connect(target)) as connection:
            row = connection.execute("SELECT value FROM counters WHERE key = ?", (f"{_today()}|{name}",)).fetchone()
        return int(row[0]) if row else 0
    except (OSError, sqlite3.Error):
        return 0


def history(days: int, path: Path | None = None) -> dict[str, dict[str, int]]:
    """`{date: {name: value}}` for the last `days` days, today included."""
    target = path or DB
    start = (datetime.now(timezone.utc).date() - timedelta(days=max(days, 1) - 1)).isoformat()
    result: dict[str, dict[str, int]] = {}
    if not target.exists():
        return result
    try:
        with closing(_connect(target)) as connection:
            for key, value in connection.execute("SELECT key, value FROM counters WHERE key >= ?", (start,)):
                date, _, name = key.partition("|")
                result.setdefault(date, {})[name] = int(value)
    except (OSError, sqlite3.Error):
        return {}
    return result


def safe_name(text: str) -> str:
    """A counter-name part from user text: lowercase letters, digits and `@._-`, at most 80 characters."""
    return re.sub(r"[^a-z0-9@._-]", "_", text.lower())[:80] or "unknown"
