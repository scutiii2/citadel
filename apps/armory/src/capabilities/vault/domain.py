"""Search and read the Obsidian vault, read-only and markdown only.
Paths go through `ConfinedRoot`, so `.obsidian`, `.git` and secret-like files are unreachable."""

from __future__ import annotations

from pathlib import Path

from src.capabilities.vault.contract import NoteHit, NoteListResult, NoteResult, VaultSearchResult
from src.services import untrusted
from src.services.confined_paths import ConfinedRoot, PathRefused

MAX_RESULTS = 50
MAX_PER_NOTE = 3
MAX_LIST = 300
MAX_NOTE_BYTES = 24_000
MAX_SCAN_BYTES = 400_000
MAX_LINE_CHARS = 300


def open_vault(vault_dir: Path) -> ConfinedRoot:
    if not vault_dir.is_dir():
        raise FileNotFoundError(f"No vault folder at {vault_dir.resolve()}. Set MCP_VAULT_DIR in .env.")
    return ConfinedRoot(vault_dir, (".md",))


def _clip(line: str) -> str:
    line = line.strip()
    return line if len(line) <= MAX_LINE_CHARS else line[: MAX_LINE_CHARS - 3] + "..."


class VaultDesk:
    """Search and read one Obsidian vault folder; every path is confined to it."""

    def __init__(self, vault: ConfinedRoot) -> None:
        self._vault = vault

    def search(self, query: str, folder: str = "", max_results: int = 15) -> VaultSearchResult:
        needle = query.strip().lower()
        if not needle:
            raise ValueError("query must not be empty")
        if not 1 <= max_results <= MAX_RESULTS:
            raise ValueError(f"max_results must be between 1 and {MAX_RESULTS}, not {max_results}")
        start = self._folder(folder)
        hits: list[NoteHit] = []
        for path in self._vault.walk_files(start):
            if len(hits) >= max_results:
                break
            rel = self._vault.relative(path)
            if needle in path.stem.lower():
                hits.append(NoteHit(path=rel, line=0, text=path.stem))
            found = 0
            text = path.read_bytes()[:MAX_SCAN_BYTES].decode("utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                if needle in line.lower():
                    hits.append(NoteHit(path=rel, line=number, text=_clip(line)))
                    found += 1
                    if found >= MAX_PER_NOTE or len(hits) >= max_results:
                        break
        notes = len({hit.path for hit in hits})
        message = f"{len(hits)} matches in {notes} notes for {query!r}." if hits else f"No notes match {query!r}."
        return VaultSearchResult(query=query, hits=hits, message=message)

    def list_notes(self, folder: str = "") -> NoteListResult:
        start = self._folder(folder)
        notes = [self._vault.relative(path) for path in self._vault.walk_files(start)]
        shown = notes[:MAX_LIST]
        note = f" Showing the first {MAX_LIST}; give a narrower folder." if len(notes) > MAX_LIST else ""
        return NoteListResult(folder=folder.strip(), notes=shown, message=f"{len(notes)} notes.{note}")

    def read_note(self, path: str) -> NoteResult:
        if not path.strip().lower().endswith(".md"):
            raise PathRefused("Only .md notes are read here.")
        target = self._vault.resolve(path)
        if not target.is_file():
            raise FileNotFoundError(f"No note at {path!r}. Use the vault search or list to find the exact path.")
        text = target.read_text(encoding="utf-8", errors="replace")
        rel = self._vault.relative(target)
        content = untrusted.fenced_and_capped(text, source=f"vault note {rel}", max_bytes=MAX_NOTE_BYTES)
        return NoteResult(path=rel, content=content, message=f"Read {rel} ({len(text)} characters).")

    def _folder(self, folder: str) -> Path:
        target = self._vault.resolve(folder)
        if not target.is_dir():
            raise PathRefused(f"{folder!r} is not a folder in the vault.")
        return target
