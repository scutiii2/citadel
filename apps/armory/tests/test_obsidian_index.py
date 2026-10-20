"""Real SQLite hybrid index with deterministic local embeddings and a temporary vault."""
from __future__ import annotations

import asyncio
import threading

import pytest

from src.capabilities.obsidian.utils.chunking import chunk_note
from src.capabilities.obsidian.utils.index import VaultIndex
from src.capabilities.obsidian.utils.index_store import SqliteIndexStore
from src.services.obsidian_index import IndexRuntime


class FakeEmbedder:
    identity = "fake-v1"

    def __init__(self):
        self.calls = []
        self.fail = False

    def embed(self, texts):
        if self.fail:
            raise RuntimeError("offline")
        self.calls.extend(texts)
        return [[1.0, 0.0] if "cat" in t.lower() or "feline" in t.lower() else [0.0, 1.0] for t in texts]


@pytest.fixture
def library(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    embedder = FakeEmbedder()
    store = SqliteIndexStore(tmp_path / "index.db", embedder.identity)
    return vault, embedder, store, VaultIndex(vault, embedder, store)


def test_heading_chunking_retains_metadata_and_ignores_code_headings():
    text = "---\ntags: [pets, home]\nagent: Ember\n---\n# Care\nIntro [[Memory/Cats#Food|cats]].\n## Food\n"
    text += "```md\n# not a heading\n```\n" + "cats need good food. " * 250
    chunks = chunk_note("Memory/Care.md", text)
    assert len(chunks) > 2
    assert chunks[0].heading == ("Care",)
    assert all(c.heading == ("Care", "Food") for c in chunks[1:])
    assert all(len(c.text) <= 2000 for c in chunks)
    assert all(set(c.tags) == {"pets", "home"} and c.frontmatter["agent"] == "Ember" for c in chunks)
    assert all(c.wikilinks == ["Memory/Cats"] for c in chunks)
    assert "not a heading" in "".join(c.text for c in chunks)


def test_incremental_refresh_content_hash_changes_and_deletion(library):
    vault, embedder, store, index = library
    note = vault / "cats.md"
    note.write_text("# Cats\nfeline care", encoding="utf-8")
    assert index.refresh()["updated"] == 1
    count = len(embedder.calls)
    assert index.refresh()["updated"] == 0
    note.touch()
    assert index.refresh()["updated"] == 0
    assert len(embedder.calls) == count
    note.write_text("# Cats\ncat food", encoding="utf-8")
    assert index.refresh()["updated"] == 1
    assert len(embedder.calls) > count
    note.unlink()
    assert index.refresh()["deleted"] == 1
    assert not store.states()
    assert not index.search("cats", 5)


def test_embedding_failure_keeps_previous_note_and_does_not_mark_refresh_done(library):
    vault, embedder, _, index = library
    note = vault / "cats.md"
    note.write_text("cat care", encoding="utf-8")
    index.refresh()
    embedder.fail = True
    note.write_text("changed text", encoding="utf-8")
    with pytest.raises(RuntimeError):
        index.refresh()
    embedder.fail = False
    assert index.search("cat care", 3)[0][0].text == "cat care"
    assert index.refresh()["updated"] == 1


def test_bm25_vectors_and_wikilink_boost(library):
    vault, _, _, index = library
    (vault / "Cats.md").write_text("# Cats\ncat care [[Food]]", encoding="utf-8")
    (vault / "Food.md").write_text("# Diet\nprotein nutrition", encoding="utf-8")
    (vault / "Other.md").write_text("gardening soil", encoding="utf-8")
    index.refresh()
    results = index.search("feline", 3)
    assert results[0][0].path == "Cats.md"  # vector-only synonym
    assert next(score for chunk, score in results if chunk.path == "Food.md") > next(
        score for chunk, score in results if chunk.path == "Other.md"
    )
    assert index.search("nutrition", 1)[0][0].path == "Food.md"  # BM25 exact word


def test_no_hidden_files_or_symlink_escape_are_indexed(library, tmp_path):
    vault, _, store, index = library
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian/private.md").write_text("private", encoding="utf-8")
    (vault / "secrets").mkdir()
    (vault / "secrets/private.md").write_text("private", encoding="utf-8")
    (vault / "note.txt").write_text("ignored", encoding="utf-8")
    (vault / "good.md").write_text("public", encoding="utf-8")
    index.refresh()
    assert set(store.states()) == {"good.md"}


def test_store_reopens_and_rejects_model_change(library, tmp_path):
    vault, embedder, _, index = library
    (vault / "good.md").write_text("cat care", encoding="utf-8")
    index.refresh()
    reopened = SqliteIndexStore(tmp_path / "index.db", embedder.identity)
    assert reopened.states()["good.md"][2]
    with pytest.raises(ValueError, match="model"):
        SqliteIndexStore(tmp_path / "index.db", "different-model")


def test_background_refresh_does_not_block_event_loop_or_search():
    entered, release = threading.Event(), threading.Event()

    class SlowIndex:
        def refresh(self):
            entered.set()
            release.wait(3)
            return {"updated": 0, "deleted": 0}

        def search(self, query, top_k):
            return []

    async def check():
        runtime = IndexRuntime(SlowIndex(), interval=60)
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            assert runtime.search("cat", 3) == []
            await asyncio.wait_for(asyncio.sleep(0), timeout=0.1)
            assert runtime.refreshing
        finally:
            release.set()
            await asyncio.to_thread(runtime.close)

    asyncio.run(check())
