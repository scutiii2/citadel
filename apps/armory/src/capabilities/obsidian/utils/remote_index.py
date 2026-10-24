"""Bounded recursive REST source sharing the mounted index's chunking and ranking."""
import hashlib
from pathlib import Path

from src.capabilities.obsidian.utils.chunking import chunk_note
from src.capabilities.obsidian.utils.gateway import vault_path
from src.capabilities.obsidian.utils.index import VaultIndex


class RemoteVaultIndex(VaultIndex):
    def __init__(self, gateway, embedder, store, check=lambda: None):
        super().__init__(Path("."), embedder, store)
        self.gateway, self.check = gateway, check

    def refresh(self):
        states, seen, folders = self.store.states(), set(), [""]
        updated, total = 0, 0
        while folders:
            self.check()
            parent = folders.pop()
            children = self.gateway.list(parent)
            total += len(children)
            if total > 10_000 or len(parent.split("/")) > 32:
                raise ValueError("Vault enumeration limit reached; previous completed documents retained")
            for child in children:
                if child.startswith(".") or child.rstrip("/") in {"secrets", "node_modules"}:
                    continue
                if "/" in child.rstrip("/"):
                    raise ValueError("Invalid immediate child")
                path = (parent + "/" if parent else "") + child
                if child.endswith("/"):
                    folders.append(vault_path(path, folder=True))
                    continue
                if not child.lower().endswith(".md"):
                    continue
                path = vault_path(path, markdown=True)
                self.check()
                text = self.gateway.read(path)
                raw = text.encode("utf-8")
                digest = hashlib.sha256(raw).hexdigest()
                seen.add(path)
                if path in states and states[path][2] == digest:
                    continue
                chunks, vectors = chunk_note(path, text), []
                for start in range(0, len(chunks), 16):
                    self.check()
                    vectors.extend(self.embedder.embed([" / ".join(c.heading) + "\n" + c.text
                                                       for c in chunks[start:start + 16]]))
                self.check()
                self.store.replace(path, (0, len(raw), digest), chunks, vectors)
                updated += 1
        self.check()
        # Only a complete traversal authorizes removing unseen documents.
        deleted = set(states) - seen
        for path in deleted:
            self.store.remove(path)
        return {"updated": updated, "deleted": len(deleted)}
