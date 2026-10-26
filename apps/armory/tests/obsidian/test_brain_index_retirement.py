import json
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

from src.capabilities.obsidian.utils import brain_indexes
from src.capabilities.obsidian.utils.brain_indexes import Entry, ScopedIndexes


def test_repeated_retirement_never_unlinks_a_retiring_workers_database(tmp_path, monkeypatch):
    monkeypatch.setattr(brain_indexes, "settings", replace(brain_indexes.settings, obsidian_index_path=tmp_path / "index.db"))
    path = tmp_path / "brains" / "generation" / "index.db"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"owned derived state")
    (path.parent / "owner.json").write_text(json.dumps({"owner": "alice", "connection": "personal-id"}), encoding="utf-8")
    release = threading.Event()
    worker = threading.Thread(target=lambda: release.wait(5), daemon=True)
    worker.start()
    runtime = SimpleNamespace(_thread=worker, _stop=threading.Event())
    registry = ScopedIndexes()
    key = ("personal-id", "gen", "model")
    registry.entries[key] = Entry(runtime, "alice", "personal-id", path, time.monotonic())
    try:
        registry.retire("alice")
        assert key in registry.retiring and key not in registry.entries
        registry.retire("alice")
        assert path.exists() and (path.parent / "owner.json").exists()
    finally:
        release.set()
        worker.join(timeout=2)
        registry._closed.set()
