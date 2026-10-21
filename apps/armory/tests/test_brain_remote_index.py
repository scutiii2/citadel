import pytest

from src.capabilities.obsidian.utils.remote_index import RemoteVaultIndex
from src.capabilities.obsidian.utils.index_store import SqliteIndexStore
from tests.test_obsidian_index import FakeEmbedder


class Vault:
    def __init__(self):
        self.files = {"Cats.md": "# Cats\ncat care", "Folder/Food.md": "# Food\ncat food"}
        self.fail = False

    def list(self, path):
        if path and self.fail:
            raise OSError("offline")
        return ["Food.md"] if path else ["Cats.md", "Folder/"]

    def read(self, path):
        return self.files[path]


def test_remote_refresh_incremental_partial_scan_retains_previous(tmp_path):
    vault, embedder = Vault(), FakeEmbedder()
    store = SqliteIndexStore(tmp_path / "remote.db", embedder.identity)
    index = RemoteVaultIndex(vault, embedder, store)
    assert index.refresh() == {"updated": 2, "deleted": 0}
    calls = len(embedder.calls)
    assert index.refresh()["updated"] == 0 and len(embedder.calls) == calls
    vault.fail = True
    with pytest.raises(OSError):
        index.refresh()
    assert len(store.states()) == 2
    assert index.search("cat", 3)
    vault.fail = False
    vault.list = lambda path: ["Cats.md"]
    assert index.refresh()["deleted"] == 1


def test_cancelled_generation_never_attaches_documents(tmp_path):
    vault, embedder = Vault(), FakeEmbedder()
    store = SqliteIndexStore(tmp_path / "cancel.db", embedder.identity)
    def revoked():
        raise ValueError("obsolete generation")
    index = RemoteVaultIndex(vault, embedder, store, check=revoked)
    with pytest.raises(ValueError):
        index.refresh()
    assert not store.states()
