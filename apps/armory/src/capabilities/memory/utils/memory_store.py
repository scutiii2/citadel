"""Per-user memory notes in SQLite, searched with FTS5.
Every function takes the owner explicitly; reading never creates the database; text is never logged."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MAX_NOTE_CHARS = 500
MAX_NOTES = 200
DEFAULT_LIMIT = 10
MAX_QUERY_WORDS = 10
# Shorter query words match whole words only: "a"* would match nearly every note.
_PREFIX_MIN = 3

_NO_OWNER = "No account identity is known for this request, so memory is unavailable."


class MemoryStoreError(ValueError):
    """A request memory cannot honour; the message is safe to show the model."""


class MemoryConflict(MemoryStoreError):
    """The note changed, or the replacement would duplicate another note."""


@dataclass(frozen=True)
class Note:
    id: int
    text: str
    created_at: str


@dataclass(frozen=True)
class SaveOutcome:
    id: int
    duplicate: bool


def _owner(owner: str | None) -> str:
    clean = (owner or "").strip()
    if not clean:
        raise MemoryStoreError(_NO_OWNER)
    return clean


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, owner TEXT NOT NULL, text TEXT NOT NULL,
            norm TEXT NOT NULL, created_at TEXT NOT NULL
        )"""
    )
    db.execute("CREATE INDEX IF NOT EXISTS notes_owner_norm ON notes (owner, norm)")
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(text)")
    return db


def _fts_expression(query: str) -> str:
    """Quote every word so user text is never read as FTS syntax; OR them for recall.
    Words of 3+ characters also match longer words starting with them (no stemming)."""
    words = re.findall(r"\w+", query or "")[:MAX_QUERY_WORDS]
    return " OR ".join(f'"{word}"*' if len(word) >= _PREFIX_MIN else f'"{word}"' for word in words)


def save(path: Path, owner: str, text: str) -> SaveOutcome:
    """Store one note; an identical note (ignoring case and spacing) is not stored twice."""
    owner = _owner(owner)
    clean = " ".join(str(text or "").split())
    if not clean:
        raise MemoryStoreError("The note is empty.")
    if len(clean) > MAX_NOTE_CHARS:
        raise MemoryStoreError(
            f"The note is {len(clean)} characters; the limit is {MAX_NOTE_CHARS}. Shorten it."
        )
    norm = clean.lower()
    with closing(_connect(path)) as db, db:
        # One writer at a time, so the duplicate and cap checks cannot race the insert.
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT id FROM notes WHERE owner = ? AND norm = ?", (owner, norm)).fetchone()
        if row is not None:
            return SaveOutcome(id=row["id"], duplicate=True)
        count = db.execute("SELECT COUNT(*) FROM notes WHERE owner = ?", (owner,)).fetchone()[0]
        if count >= MAX_NOTES:
            raise MemoryStoreError(f"You already have {MAX_NOTES} saved notes. Forget one first.")
        cursor = db.execute(
            "INSERT INTO notes (owner, text, norm, created_at) VALUES (?, ?, ?, ?)",
            (owner, clean, norm, datetime.now(timezone.utc).isoformat()),
        )
        db.execute("INSERT INTO notes_fts (rowid, text) VALUES (?, ?)", (cursor.lastrowid, clean))
        return SaveOutcome(id=cursor.lastrowid, duplicate=False)


def search(path: Path, owner: str, query: str = "", limit: int = DEFAULT_LIMIT) -> list[Note]:
    """Ranked matches for `query`, or the newest notes when the query has no words."""
    owner = _owner(owner)
    if not path.exists():
        return []
    expression = _fts_expression(query)
    with closing(_connect(path)) as db:
        if not expression:
            rows = db.execute(
                "SELECT id, text, created_at FROM notes WHERE owner = ? ORDER BY id DESC LIMIT ?",
                (owner, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT n.id, n.text, n.created_at FROM notes_fts "
                "JOIN notes n ON n.id = notes_fts.rowid "
                "WHERE notes_fts MATCH ? AND n.owner = ? ORDER BY notes_fts.rank LIMIT ?",
                (expression, owner, limit),
            ).fetchall()
    return [Note(id=r["id"], text=r["text"], created_at=r["created_at"]) for r in rows]


def forget(path: Path, owner: str, note_id: int) -> bool:
    """Delete one of the owner's notes; False when it does not exist or is not theirs."""
    owner = _owner(owner)
    if not path.exists():
        return False
    with closing(_connect(path)) as db, db:
        row = db.execute("SELECT id FROM notes WHERE id = ? AND owner = ?", (note_id, owner)).fetchone()
        if row is None:
            return False
        db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        db.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
        return True


def update(path: Path, owner: str, note_id: int, text: str, expected_text: str) -> Note | None:
    """Atomically edit an owner's memory and its search index, refusing stale or duplicate text."""
    owner = _owner(owner)
    clean = " ".join(text.split())
    if not clean or len(clean) > MAX_NOTE_CHARS:
        raise MemoryStoreError(f"Memory must contain 1 to {MAX_NOTE_CHARS} characters.")
    if not path.exists():
        return None
    with closing(_connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT text, created_at FROM notes WHERE owner = ? AND id = ?", (owner, note_id)).fetchone()
        if row is None:
            return None
        if row["text"] != expected_text:
            raise MemoryConflict("This memory changed since you opened it. Reload before editing again.")
        duplicate = db.execute("SELECT id FROM notes WHERE owner = ? AND norm = ? AND id != ?",
                               (owner, clean.lower(), note_id)).fetchone()
        if duplicate is not None:
            raise MemoryConflict("Another memory already contains that text.")
        db.execute("UPDATE notes SET text = ?, norm = ? WHERE owner = ? AND id = ?",
                   (clean, clean.lower(), owner, note_id))
        db.execute("DELETE FROM notes_fts WHERE rowid = ?", (note_id,))
        db.execute("INSERT INTO notes_fts (rowid, text) VALUES (?, ?)", (note_id, clean))
        return Note(id=note_id, text=clean, created_at=row["created_at"])


def purge_owner(path: Path, owner: str) -> int:
    """Delete every note of `owner` (their account was deleted); returns how many."""
    owner = _owner(owner)
    if not path.exists():
        return 0
    with closing(_connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        ids = [row["id"] for row in db.execute("SELECT id FROM notes WHERE owner = ?", (owner,))]
        db.executemany("DELETE FROM notes_fts WHERE rowid = ?", [(note_id,) for note_id in ids])
        db.execute("DELETE FROM notes WHERE owner = ?", (owner,))
    return len(ids)
