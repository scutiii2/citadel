"""Bounded, leased generation runtimes. Derived data is never a vault source."""
import atexit
import hashlib
import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from src.config import settings
from src.capabilities.obsidian.utils import brain_resolver
from src.capabilities.obsidian.utils.obsidian_index import IndexRuntime, get_runtime

_embedding_slots = threading.BoundedSemaphore(2)
_refresh_slots = threading.BoundedSemaphore(2)


class BoundedEmbedder:
    def __init__(self, delegate):
        self.delegate, self.identity = delegate, delegate.identity

    def embed(self, texts):
        with _embedding_slots:
            return self.delegate.embed(texts)


@dataclass
class Entry:
    runtime: IndexRuntime
    uid: str
    connection: str
    path: Path
    touched: float
    readers: int = 0
    retired: bool = False


class ScopedIndexes:
    def __init__(self):
        self.entries = {}
        self.retiring = {}
        self.lock = threading.RLock()
        self._closed = threading.Event()
        threading.Thread(target=self._reap, name="brain-index-reaper", daemon=True).start()

    def _reap(self):
        while not self._closed.wait(60):
            with self.lock:
                for key, entry in list(self.entries.items()):
                    if not entry.readers and (entry.runtime._stop.is_set() or time.monotonic() - entry.touched > 900):
                        self._discard(key)

    def _new(self, snapshot, uid):
        from src.capabilities.obsidian.utils.embeddings import OllamaEmbedder
        from src.capabilities.obsidian.utils.index_store import SqliteIndexStore
        from src.capabilities.obsidian.utils.remote_index import RemoteVaultIndex
        embedder = BoundedEmbedder(OllamaEmbedder(settings.obsidian_ollama_url, settings.obsidian_embed_model))
        key = hashlib.sha256((snapshot["id"] + snapshot["generation"] + embedder.identity).encode()).hexdigest()
        path = settings.obsidian_index_path.parent / "brains" / key / "index.db"
        if settings.obsidian_vault_path and path.resolve().is_relative_to(Path(settings.obsidian_vault_path).resolve()):
            raise ValueError("Derived brain indexes must be outside the source vault")
        store = SqliteIndexStore(path, embedder.identity)
        (path.parent / "owner.json").write_text(json.dumps({"owner": uid if snapshot["scope"] == "personal" else "",
            "connection": snapshot["id"], "generation": snapshot["generation"]}), encoding="utf-8")
        stopped = threading.Event()

        def check():
            if stopped.is_set():
                raise ValueError("Retired index")
            try:
                current = brain_resolver.resolve(snapshot["scope"], "read", uid)
                if current["generation"] != snapshot["generation"]:
                    raise ValueError("Obsolete generation")
            except Exception:
                stopped.set()
                raise ValueError("Brain authorization changed") from None

        source = RemoteVaultIndex(brain_resolver.gateway(snapshot), embedder, store, check)
        # Refresh concurrency is shared across every personal and instance index.
        class ScheduledIndex:
            def refresh(self):
                if not _refresh_slots.acquire(blocking=False):
                    return
                try:
                    return source.refresh()
                finally:
                    _refresh_slots.release()

            def search(self, query, count):
                return source.search(query, count)
        runtime = IndexRuntime(ScheduledIndex(), settings.obsidian_refresh_seconds, stop=stopped)
        return Entry(runtime, uid, snapshot["id"], path, time.monotonic())

    @contextmanager
    def lease(self, snapshot, uid):
        if snapshot["source"] == "legacy":
            yield get_runtime(settings)
            return
        key = (snapshot["id"], snapshot["generation"], settings.obsidian_embed_model)
        with self.lock:
            if key in self.retiring:
                raise ValueError("Previous index readers are closing; retry shortly")
            if key in self.entries and self.entries[key].runtime._stop.is_set():
                entry = self.entries[key]
                entry.retired = True
                if not entry.readers:
                    self._discard(key)
                raise ValueError("Index authorization was refreshed; retry shortly")
            now = time.monotonic()
            for old_key, old in list(self.entries.items()):
                if old_key != key and (old.connection == snapshot["id"] or now - old.touched > 900):
                    old.retired = True
                    old.runtime._stop.set()
                    if not old.readers:
                        self._discard(old_key)
            if key not in self.entries:
                if len(self.entries) + len(self.retiring) >= 8:
                    free = [(k, v) for k, v in self.entries.items() if not v.readers]
                    if not free:
                        raise ValueError("Brain index capacity is busy; retry shortly")
                    self._discard(min(free, key=lambda pair: pair[1].touched)[0])
                    raise ValueError("An idle index is closing; retry shortly")
                self.entries[key] = self._new(snapshot, uid)
            entry = self.entries[key]
            entry.readers += 1
            entry.touched = now
        try:
            yield entry.runtime
        finally:
            with self.lock:
                entry.readers -= 1
                if entry.retired and not entry.readers:
                    self._discard(key)

    def _discard(self, key):
        entry = self.entries.pop(key)
        self.retiring[key] = entry
        entry.runtime._stop.set()
        # Cleanup waits off the request path, after worker and active readers end.
        def clean():
            entry.runtime._thread.join()
            for suffix in ("", "-wal", "-shm"):
                try:
                    Path(str(entry.path) + suffix).unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                (entry.path.parent / "owner.json").unlink(missing_ok=True)
            except OSError:
                pass
            with self.lock:
                self.retiring.pop(key, None)
        threading.Thread(target=clean, name="brain-index-retire", daemon=True).start()

    def status(self, snapshot):
        key = (snapshot["id"], snapshot["generation"], settings.obsidian_embed_model)
        with self.lock:
            entry = self.entries.get(key)
            if entry is None:
                return "not_started"
            if entry.runtime._stop.is_set():
                return "retired"
            if entry.runtime.error:
                return "refresh_failed"
            return "indexing" if entry.runtime.refreshing else "ready"

    def retire(self, uid, scope="personal"):
        with self.lock:
            active_paths = {e.path.parent.resolve() for e in [*self.entries.values(), *self.retiring.values()]}
            for key, entry in list(self.entries.items()):
                if (scope == "instance" and entry.connection == "instance") or (scope == "personal" and entry.uid == uid and entry.connection != "instance"):
                    entry.retired = True
                    entry.runtime._stop.set()
                    if not entry.readers:
                        self._discard(key)
        if scope == "instance":
            from src.capabilities.obsidian.utils.obsidian_index import close_runtime
            close_runtime()
        # Account cleanup also removes derived state left by earlier processes.
        root = (settings.obsidian_index_path.parent / "brains").resolve()
        if root.is_dir():
            for manifest in root.glob("*/owner.json"):
                if manifest.parent.resolve() in active_paths or manifest.is_symlink() or not manifest.parent.resolve().is_relative_to(root):
                    continue
                try:
                    owner = json.loads(manifest.read_text(encoding="utf-8"))
                    matches = owner.get("owner") == uid if scope == "personal" else owner.get("connection") == "instance"
                    if not matches:
                        continue
                    with self.lock:
                        if any(e.path.parent.resolve() == manifest.parent.resolve() for e in [*self.entries.values(), *self.retiring.values()]):
                            continue
                        for name in ("index.db", "index.db-wal", "index.db-shm", "owner.json"):
                            (manifest.parent / name).unlink(missing_ok=True)
                except (OSError, ValueError):
                    continue


indexes = ScopedIndexes()
atexit.register(lambda: [entry.runtime._stop.set() for entry in list(indexes.entries.values())])
