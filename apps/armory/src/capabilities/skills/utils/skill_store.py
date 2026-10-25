"""Per-user learned skills in SQLite, searched with FTS5.
A proposal is `proposed` and hidden from `search` until the user makes it `active`; functions take the owner explicitly, and skill text is never logged."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MAX_TITLE_CHARS = 80
MAX_WHEN_CHARS = 300
MAX_STEPS_CHARS = 1200
MAX_TOOLS_CHARS = 200
MAX_ACTIVE = 50
MAX_PROPOSED = 20
DEFAULT_LIMIT = 3
MAX_QUERY_WORDS = 10
# Shorter query words match whole words only: "a"* would match nearly every skill.
_PREFIX_MIN = 3

# A skill that failed this often, and more often than it worked, is no longer offered to the
# model; the user edits it (which resets the counts) or retires it. See is_failing.
FAILING_MIN = 3

PROPOSED, ACTIVE, RETIRED = "proposed", "active", "retired"
STATUSES = (PROPOSED, ACTIVE, RETIRED)
SUCCESS, FAILURE = "success", "failure"

_NO_OWNER = "No account identity is known for this request, so skills are unavailable."


class SkillStoreError(ValueError):
    """A request the skill store cannot honour; the message is safe to show the model."""


class SkillConflict(SkillStoreError):
    """The change clashes with another skill or a cap (a duplicate title, too many active skills)."""


@dataclass(frozen=True)
class Skill:
    id: int
    title: str
    when_to_use: str
    steps: str
    tools: str
    status: str
    successes: int
    failures: int
    created_at: str


@dataclass(frozen=True)
class ProposeOutcome:
    id: int
    duplicate: bool


_COLUMNS = "id, title, when_to_use, steps, tools, status, successes, failures, created_at"
# The SQL form of is_failing, for queries that must leave failing skills out.
_NOT_FAILING = f"NOT (failures >= {FAILING_MIN} AND failures > successes)"


def is_failing(skill: Skill) -> bool:
    """Whether the skill failed at least FAILING_MIN times, and more often than it worked."""
    return skill.failures >= FAILING_MIN and skill.failures > skill.successes


def _owner(owner: str | None) -> str:
    clean = (owner or "").strip()
    if not clean:
        raise SkillStoreError(_NO_OWNER)
    return clean


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, title TEXT NOT NULL,
            when_to_use TEXT NOT NULL, steps TEXT NOT NULL, tools TEXT NOT NULL, norm TEXT NOT NULL,
            status TEXT NOT NULL, successes INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )"""
    )
    db.execute("CREATE INDEX IF NOT EXISTS skills_owner_norm ON skills (owner, norm)")
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(body)")
    return db


def _fts_expression(query: str) -> str:
    """Quote every word so user text can never be read as FTS syntax; OR them for recall."""
    words = re.findall(r"\w+", query or "")[:MAX_QUERY_WORDS]
    return " OR ".join(f'"{word}"*' if len(word) >= _PREFIX_MIN else f'"{word}"' for word in words)


def _clean(label: str, text: str, limit: int, required: bool = True) -> str:
    clean = " ".join(str(text or "").split())
    if required and not clean:
        raise SkillStoreError(f"The {label} is empty.")
    if len(clean) > limit:
        raise SkillStoreError(f"The {label} is {len(clean)} characters; the limit is {limit}. Shorten it.")
    return clean


def _row(row: sqlite3.Row) -> Skill:
    return Skill(**{key: row[key] for key in row.keys()})


def propose(path: Path, owner: str, title: str, when_to_use: str, steps: str, tools: str = "") -> ProposeOutcome:
    """Store a `proposed` skill; the same title (ignoring case and spacing) is not stored twice."""
    owner = _owner(owner)
    title = _clean("title", title, MAX_TITLE_CHARS)
    when_to_use = _clean("when_to_use text", when_to_use, MAX_WHEN_CHARS)
    steps = _clean("steps", steps, MAX_STEPS_CHARS)
    tools = _clean("tools list", tools, MAX_TOOLS_CHARS, required=False)
    norm = title.lower()
    with closing(_connect(path)) as db, db:
        # One writer at a time, so the duplicate and cap checks cannot race the insert.
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT id FROM skills WHERE owner = ? AND norm = ? AND status != ?",
                         (owner, norm, RETIRED)).fetchone()
        if row is not None:
            return ProposeOutcome(id=row["id"], duplicate=True)
        waiting = db.execute("SELECT COUNT(*) FROM skills WHERE owner = ? AND status = ?", (owner, PROPOSED)).fetchone()[0]
        if waiting >= MAX_PROPOSED:
            raise SkillStoreError(f"You already have {MAX_PROPOSED} skills waiting for approval. Ask the user to review them first.")
        cursor = db.execute(
            "INSERT INTO skills (owner, title, when_to_use, steps, tools, norm, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (owner, title, when_to_use, steps, tools, norm, PROPOSED, datetime.now(timezone.utc).isoformat()),
        )
        db.execute("INSERT INTO skills_fts (rowid, body) VALUES (?, ?)", (cursor.lastrowid, f"{title} {when_to_use} {steps}"))
        return ProposeOutcome(id=cursor.lastrowid, duplicate=False)


def search(path: Path, owner: str, query: str = "", limit: int = DEFAULT_LIMIT) -> list[Skill]:
    """Ranked `active` skills for `query`, or the newest active ones when the query has no words.
    Proposed, retired and failing skills are never returned here."""
    owner = _owner(owner)
    if not path.exists():
        return []
    expression = _fts_expression(query)
    with closing(_connect(path)) as db:
        if not expression:
            rows = db.execute(
                f"SELECT {_COLUMNS} FROM skills WHERE owner = ? AND status = ? AND {_NOT_FAILING} ORDER BY id DESC LIMIT ?",
                (owner, ACTIVE, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT s.id, s.title, s.when_to_use, s.steps, s.tools, s.status, s.successes, s.failures, s.created_at "
                "FROM skills_fts JOIN skills s ON s.id = skills_fts.rowid "
                f"WHERE skills_fts MATCH ? AND s.owner = ? AND s.status = ? AND {_NOT_FAILING} "
                "ORDER BY skills_fts.rank LIMIT ?",
                (expression, owner, ACTIVE, limit),
            ).fetchall()
    return [_row(r) for r in rows]


def update(path: Path, owner: str, skill_id: int, title: str, when_to_use: str, steps: str, tools: str = "") -> Skill | None:
    """Rewrite one of the owner's skills; None when it is not theirs. Status stays, counts reset, search index follows.
    Called from the user's side only, never from a model tool."""
    owner = _owner(owner)
    title = _clean("title", title, MAX_TITLE_CHARS)
    when_to_use = _clean("when_to_use text", when_to_use, MAX_WHEN_CHARS)
    steps = _clean("steps", steps, MAX_STEPS_CHARS)
    tools = _clean("tools list", tools, MAX_TOOLS_CHARS, required=False)
    if not path.exists():
        return None
    norm = title.lower()
    with closing(_connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM skills WHERE id = ? AND owner = ?", (skill_id, owner)).fetchone() is None:
            return None
        if db.execute("SELECT 1 FROM skills WHERE owner = ? AND norm = ? AND status != ? AND id != ?",
                      (owner, norm, RETIRED, skill_id)).fetchone() is not None:
            raise SkillConflict("Another skill already has that title.")
        db.execute("UPDATE skills SET title = ?, when_to_use = ?, steps = ?, tools = ?, norm = ?, "
                   "successes = 0, failures = 0 WHERE id = ?", (title, when_to_use, steps, tools, norm, skill_id))
        db.execute("DELETE FROM skills_fts WHERE rowid = ?", (skill_id,))
        db.execute("INSERT INTO skills_fts (rowid, body) VALUES (?, ?)", (skill_id, f"{title} {when_to_use} {steps}"))
        return _row(db.execute(f"SELECT {_COLUMNS} FROM skills WHERE id = ?", (skill_id,)).fetchone())


def list_skills(path: Path, owner: str, status: str | None = None) -> list[Skill]:
    """Every skill of the owner (newest first), optionally one status. For the user's own review page."""
    owner = _owner(owner)
    if status is not None and status not in STATUSES:
        raise SkillStoreError(f"Unknown status {status!r}.")
    if not path.exists():
        return []
    sql, args = f"SELECT {_COLUMNS} FROM skills WHERE owner = ?", [owner]
    if status:
        sql, args = sql + " AND status = ?", args + [status]
    with closing(_connect(path)) as db:
        return [_row(r) for r in db.execute(sql + " ORDER BY id DESC", args).fetchall()]


def set_status(path: Path, owner: str, skill_id: int, status: str) -> bool:
    """Approve (`active`), retire or re-propose a skill; False when it is not the owner's.
    Called from the user's side only (ember_api routes), never from a model tool."""
    owner = _owner(owner)
    if status not in STATUSES:
        raise SkillStoreError(f"Unknown status {status!r}.")
    if not path.exists():
        return False
    with closing(_connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT status FROM skills WHERE id = ? AND owner = ?", (skill_id, owner)).fetchone()
        if row is None:
            return False
        if status == ACTIVE and row["status"] != ACTIVE:
            active = db.execute("SELECT COUNT(*) FROM skills WHERE owner = ? AND status = ?", (owner, ACTIVE)).fetchone()[0]
            if active >= MAX_ACTIVE:
                raise SkillConflict(f"You already have {MAX_ACTIVE} active skills. Retire one first.")
        db.execute("UPDATE skills SET status = ? WHERE id = ?", (status, skill_id))
        return True


def mark(path: Path, owner: str, skill_id: int, outcome: str) -> Skill | None:
    """Count one use of an active skill as a success or a failure; None when no such active skill."""
    owner = _owner(owner)
    if outcome not in (SUCCESS, FAILURE):
        raise SkillStoreError(f"The outcome must be {SUCCESS!r} or {FAILURE!r}.")
    if not path.exists():
        return None
    column = "successes" if outcome == SUCCESS else "failures"
    with closing(_connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        changed = db.execute(f"UPDATE skills SET {column} = {column} + 1 WHERE id = ? AND owner = ? AND status = ?",
                             (skill_id, owner, ACTIVE)).rowcount
        if not changed:
            return None
        return _row(db.execute(f"SELECT {_COLUMNS} FROM skills WHERE id = ?", (skill_id,)).fetchone())


def delete(path: Path, owner: str, skill_id: int) -> bool:
    """Delete one of the owner's skills; False when it does not exist or is not theirs."""
    owner = _owner(owner)
    if not path.exists():
        return False
    with closing(_connect(path)) as db, db:
        if db.execute("SELECT 1 FROM skills WHERE id = ? AND owner = ?", (skill_id, owner)).fetchone() is None:
            return False
        db.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
        db.execute("DELETE FROM skills_fts WHERE rowid = ?", (skill_id,))
        return True


def purge_owner(path: Path, owner: str) -> int:
    """Delete every skill of `owner` (their account was deleted); returns how many."""
    owner = _owner(owner)
    if not path.exists():
        return 0
    with closing(_connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        ids = [row["id"] for row in db.execute("SELECT id FROM skills WHERE owner = ?", (owner,))]
        db.executemany("DELETE FROM skills_fts WHERE rowid = ?", [(i,) for i in ids])
        db.execute("DELETE FROM skills WHERE owner = ?", (owner,))
    return len(ids)
