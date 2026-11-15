"""The account's notes, read from Stronghold. Used by brains until they move there too.

Has the two reads brains need, with NotesService's names and errors.
"""

from __future__ import annotations

import json
import re

from src.models import Account
from src.services.notes import Note, NoteNotFound
from src.services.stronghold_forwarder import StrongholdForwarder, StrongholdUnavailable

_NOTE_ID = re.compile(r"[0-9a-f]{32}")


class RemoteNotes:
    def __init__(self, stronghold: StrongholdForwarder, account: Account) -> None:
        self._stronghold = stronghold
        self._account = account

    async def _read(self, path: str):
        answer = await self._stronghold.forward("GET", path, self._account)
        if answer.status == 404:
            raise NoteNotFound()
        if answer.status != 200:
            raise StrongholdUnavailable(f"stronghold answered {answer.status}")
        return json.loads(answer.body)

    async def list(self) -> list[Note]:
        return [Note.from_doc(doc) for doc in await self._read("/notes")]

    async def get(self, note_id: str) -> Note:
        if not _NOTE_ID.fullmatch(note_id):
            raise NoteNotFound()
        return Note.from_doc(await self._read(f"/notes/{note_id}"))
