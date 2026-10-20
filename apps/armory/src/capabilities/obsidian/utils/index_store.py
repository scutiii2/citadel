"""SQLite WAL + FTS5 BM25 + sqlite-vec, with short transactions and per-call connections."""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

import sqlite_vec

from src.capabilities.obsidian.utils.chunking import Chunk
from src.utils.catalog import catalog


class IndexStore(Protocol):
    def states(self) -> dict[str, tuple[int, int, str]]: ...
    def replace(self, path: str, state: tuple[int, int, str], chunks: list[Chunk], vectors: list[list[float]]) -> None: ...
    def remove(self, path: str) -> None: ...
    def candidates(self, query: str, vector: list[float], limit: int) -> list[tuple[int, Chunk, float]]: ...
    def linked(self, paths: set[str]) -> list[tuple[int, Chunk]]: ...
    def paths(self) -> list[str]: ...


@catalog
class SqliteIndexStore:
    """Persist source signatures and atomically replace a note's chunks and vectors."""

    def __init__(self, path: Path, model: str):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS documents (path TEXT PRIMARY KEY, mtime INTEGER, size INTEGER, digest TEXT);
                CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, path TEXT NOT NULL, body TEXT, metadata TEXT, vector BLOB);
                CREATE INDEX IF NOT EXISTS chunk_path ON chunks(path);
                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(body);
            """)
            previous = db.execute("SELECT value FROM meta WHERE key='model'").fetchone()
            if previous and previous[0] != model:
                raise ValueError("Embedding model changed. Configure a new OBSIDIAN_INDEX_PATH to rebuild the index.")
            db.execute("INSERT OR IGNORE INTO meta VALUES ('model', ?)", (model,))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.enable_load_extension(True)
            sqlite_vec.load(db)
            db.enable_load_extension(False)
            with db:
                yield db
        finally:
            db.close()

    def states(self) -> dict[str, tuple[int, int, str]]:
        with self.connection() as db:
            return {row[0]: tuple(row[1:]) for row in db.execute("SELECT path,mtime,size,digest FROM documents")}

    @staticmethod
    def _delete(db, path):
        db.execute("DELETE FROM chunk_fts WHERE rowid IN (SELECT id FROM chunks WHERE path=?)", (path,))
        db.execute("DELETE FROM chunks WHERE path=?", (path,))
        db.execute("DELETE FROM documents WHERE path=?", (path,))

    def replace(self, path, state, chunks, vectors):
        if len(chunks) != len(vectors):
            raise ValueError("Embedding count does not match chunks")
        with self.connection() as db:
            self._delete(db, path)
            db.execute("INSERT INTO documents VALUES (?,?,?,?)", (path, *state))
            for chunk, vector in zip(chunks, vectors, strict=True):
                row = db.execute("INSERT INTO chunks(path,body,metadata,vector) VALUES (?,?,?,?)", (
                    path, chunk.text, json.dumps(asdict(chunk)), sqlite_vec.serialize_float32(vector),
                ))
                db.execute("INSERT INTO chunk_fts(rowid,body) VALUES (?,?)", (row.lastrowid, " / ".join(chunk.heading) + "\n" + chunk.text))

    def remove(self, path):
        with self.connection() as db:
            self._delete(db, path)

    @staticmethod
    def _chunk(raw):
        data = json.loads(raw)
        data["heading"] = tuple(data["heading"])
        return Chunk(**data)

    def candidates(self, query, vector, limit):
        words = re.findall(r"\w+", query, re.UNICODE)[:32]
        scores: dict[int, float] = {}
        with self.connection() as db:
            if words:
                expression = " OR ".join('"' + word + '"' for word in words)
                for rank, (key,) in enumerate(db.execute(
                    "SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH ? ORDER BY bm25(chunk_fts),rowid LIMIT ?", (expression, limit),
                ), 1):
                    scores[key] = 1 / (60 + rank)
            for rank, (key,) in enumerate(db.execute(
                "SELECT id FROM chunks ORDER BY vec_distance_cosine(vector,?),id LIMIT ?", (sqlite_vec.serialize_float32(vector), limit),
            ), 1):
                scores[key] = scores.get(key, 0) + 1 / (60 + rank)
            return [(key, self._chunk(db.execute("SELECT metadata FROM chunks WHERE id=?", (key,)).fetchone()[0]), score) for key, score in scores.items()]

    def linked(self, paths):
        with self.connection() as db:
            results = []
            for path in sorted(paths):
                results.extend((key, self._chunk(raw)) for key, raw in db.execute("SELECT id,metadata FROM chunks WHERE path=? ORDER BY id LIMIT 3", (path,)))
            return results

    def paths(self):
        return list(self.states())
