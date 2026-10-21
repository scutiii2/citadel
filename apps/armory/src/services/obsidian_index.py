"""Process-owned periodic indexing, outside the reloadable capability like pdf_runtime.

Refresh runs in its own daemon worker; searches use independent SQLite WAL readers.
No scan, model call, or refresh waits on Armory's asyncio request-handling loop.
"""
from __future__ import annotations

import atexit
import logging
import threading
from pathlib import Path

from src.utils.catalog import catalog

logger = logging.getLogger(__name__)


@catalog
class IndexRuntime:
    def __init__(self, index, interval: float, *, stop=None):
        self.index = index
        self.interval = max(1, interval)
        self.refreshing = False
        self.error = ""
        self._stop = stop if stop is not None else threading.Event()
        self._thread = threading.Thread(target=self._run, name="obsidian-index", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            self.refreshing = True
            try:
                self.index.refresh()
                self.error = ""
            except Exception:  # noqa: BLE001 - keep previous index and retry; do not log vault content.
                self.error = "Vault refresh failed. Check the read-only mount, frontmatter, and local embedding service."
                logger.warning("obsidian: vault refresh failed; retaining the last indexed notes")
            finally:
                self.refreshing = False
            self._stop.wait(self.interval)

    def search(self, query, top_k):
        return self.index.search(query, top_k)

    def close(self):
        self._stop.set()
        self._thread.join(timeout=5)


_runtime = None
_lock = threading.Lock()


def get_runtime(settings):
    global _runtime
    with _lock:
        if _runtime is None:
            if not settings.obsidian_vault_path:
                raise ValueError("Set OBSIDIAN_VAULT_PATH to the read-only vault mount before semantic search.")
            from src.capabilities.obsidian.utils.embeddings import OllamaEmbedder
            from src.capabilities.obsidian.utils.index import VaultIndex
            from src.capabilities.obsidian.utils.index_store import SqliteIndexStore
            vault = Path(settings.obsidian_vault_path).resolve()
            if settings.obsidian_index_path.resolve().is_relative_to(vault):
                raise ValueError("OBSIDIAN_INDEX_PATH must be outside the read-only vault mount")
            embedder = OllamaEmbedder(settings.obsidian_ollama_url, settings.obsidian_embed_model)
            store = SqliteIndexStore(settings.obsidian_index_path, embedder.identity)
            _runtime = IndexRuntime(VaultIndex(vault, embedder, store), settings.obsidian_refresh_seconds)
        return _runtime


def close_runtime():
    global _runtime
    with _lock:
        if _runtime is not None:
            _runtime.close()
            _runtime = None


atexit.register(close_runtime)
