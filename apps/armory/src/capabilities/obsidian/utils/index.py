"""Incremental read-only vault scanning and hybrid ranking, independent of storage/embedding implementations."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath

from src.capabilities.obsidian.utils.chunking import Chunk, chunk_note
from src.capabilities.obsidian.utils.embeddings import Embedder
from src.capabilities.obsidian.utils.index_store import IndexStore


class VaultIndex:
    def __init__(self, vault: Path, embedder: Embedder, store: IndexStore):
        self.vault, self.embedder, self.store = vault.resolve(), embedder, store

    def refresh(self) -> dict[str, int]:
        if not self.vault.is_dir():
            raise ValueError("OBSIDIAN_VAULT_PATH must be an available read-only vault mount")
        states, seen = self.store.states(), set()
        updated = 0

        def onerror(error):
            raise error  # An incomplete scan must never delete unseen files from the index.

        for folder, directories, files in os.walk(self.vault, followlinks=False, onerror=onerror):
            directories[:] = [d for d in directories if not d.startswith(".") and d not in {"secrets", "node_modules"} and not (Path(folder) / d).is_symlink()]
            for name in sorted(files):
                note = Path(folder) / name
                if name.startswith(".") or note.suffix.lower() != ".md" or note.is_symlink() or not note.resolve().is_relative_to(self.vault):
                    continue
                path = note.relative_to(self.vault).as_posix()
                seen.add(path)
                stat = note.stat()
                if stat.st_size > 2_000_000:
                    self.store.remove(path)
                    continue
                raw = note.read_bytes()
                if note.stat().st_mtime_ns != stat.st_mtime_ns:
                    continue  # Changed during read: try again next pass.
                digest = hashlib.sha256(raw).hexdigest()
                if path in states and states[path][2] == digest:
                    continue
                chunks = chunk_note(path, raw.decode("utf-8-sig"))
                vectors = []
                for start in range(0, len(chunks), 16):
                    vectors.extend(self.embedder.embed([" / ".join(c.heading) + "\n" + c.text for c in chunks[start:start + 16]]))
                self.store.replace(path, (stat.st_mtime_ns, stat.st_size, digest), chunks, vectors)
                updated += 1
        deleted = set(states) - seen
        for path in deleted:
            self.store.remove(path)
        return {"updated": updated, "deleted": len(deleted)}

    def search(self, query: str, top_k: int) -> list[tuple[Chunk, float]]:
        if not query.strip() or not 1 <= top_k <= 20:
            raise ValueError("Give a search query and top_k between 1 and 20")
        if not self.store.states():
            return []
        candidates = self.store.candidates(query, self.embedder.embed([query])[0], max(30, top_k * 4))
        ranked = {key: (chunk, score) for key, chunk, score in candidates}
        # Resolve literal vault paths, relative links and unique basenames. Ambiguous
        # short links receive no boost rather than associating the wrong document.
        paths = set(self.store.paths())
        links: set[str] = set()
        seeds = sorted(candidates, key=lambda item: (-item[2], item[0]))[:5]
        for _, chunk, _ in seeds:
            for link in chunk.wikilinks[:20]:
                target = link if link.lower().endswith(".md") else link + ".md"
                relative = str(PurePosixPath(chunk.path).parent / target)
                matches = [p for p in paths if p == target or p == relative or ("/" not in target and PurePosixPath(p).name == target)]
                if len(matches) == 1:
                    links.add(matches[0])
        best = max((score for _, _, score in candidates), default=0.0)
        for key, chunk in self.store.linked(links):
            score = ranked.get(key, (chunk, 0.0))[1]
            # Links can promote related context, but cannot displace the best
            # direct retrieval match merely because all RRF scores are close.
            ranked[key] = (chunk, score + min(0.008, max(0.0, best * 0.99 - score)))
        return sorted(ranked.values(), key=lambda item: (-item[1], item[0].path, item[0].heading))[:top_k]
