import asyncio
import hashlib

import pytest
from cryptography.fernet import Fernet

from src.services.brain_connections import BrainConnections, BrainError, ConnectionInput
from src.services.brain_promotions import Promotions, PublicationInput, note_hash
from src.services.notes import NotesService
from src.services.secret_box import SecretBox
from tests.conftest import FakeDbGateway


class Remote:
    def __init__(self):
        self.documents = {}
        self.writes = 0
        self.fail_after_write = False

    async def operation(self, uid, operation, scope, **args):
        if operation == "read":
            if args["path"] not in self.documents:
                raise BrainError("Missing", 404)
            return {"content": self.documents[args["path"]]}
        self.writes += 1
        assert args["path"] not in self.documents
        self.documents[args["path"]] = args["text"]
        if self.fail_after_write:
            raise BrainError("Timed out", 503)
        return {"success": True}


def test_promotion_preserves_note_and_reconciles_unknown_write_outcome():
    async def scenario():
        store, remote = FakeDbGateway(), Remote()
        connections = BrainConnections(store, SecretBox(Fernet.generate_key().decode()))
        connection = await connections.save("personal", "alice", ConnectionInput(
            label="Mine", endpoint="https://vault.lan", api_key="key", allow_write=True))
        notes = NotesService(store, "alice")
        note = await notes.create("Procedure", "Useful durable instructions")
        service = Promotions(store, connections, remote, "alice", publish=False)
        body = PublicationInput(source_hash=note_hash(note), source_revision=note.updated_at,
            scope="personal", destination_revision=connection["revision"], generation=connection["generation"],
            path="Inbox/Procedure-unique.md", draft="# Procedure\nUseful durable instructions", idempotency_key="review-one")
        remote.fail_after_write = True
        with pytest.raises(BrainError):
            await service.publish(note.id, body)
        remote.fail_after_write = False
        result = await service.publish(note.id, body)
        assert result["status"] == "published" and remote.writes == 1
        assert await notes.get(note.id) == note
        assert (await service.publish(note.id, body))["id"] == result["id"]
        assert remote.writes == 1
        await notes.update(note.id, "Changed", "New content")
        with pytest.raises(BrainError, match="changed"):
            await service.publish(note.id, body)
    asyncio.run(scenario())


def test_confirmed_collision_can_reserve_a_corrected_path_without_overwriting():
    async def scenario():
        store, remote = FakeDbGateway(), Remote()
        connections = BrainConnections(store, SecretBox(Fernet.generate_key().decode()))
        destination = await connections.save("personal", "alice", ConnectionInput(
            label="Mine", endpoint="https://vault.lan", api_key="key", allow_write=True))
        note = await NotesService(store, "alice").create("Procedure", "Steps")
        service = Promotions(store, connections, remote, "alice", publish=False)
        body = PublicationInput(source_hash=note_hash(note), source_revision=note.updated_at,
            scope="personal", destination_revision=1, generation=destination["generation"],
            path="Inbox/Occupied.md", draft="# Procedure\nSteps", idempotency_key="collision")
        remote.documents[body.path] = "Another document"
        with pytest.raises(BrainError, match="different content"):
            await service.publish(note.id, body)
        assert (await service.list())[0]["status"] == "conflict"
        result = await service.publish(note.id, body.model_copy(update={"path": "Inbox/Corrected.md"}))
        assert result["path"] == "Inbox/Corrected.md" and result["status"] == "published"
        assert remote.documents[body.path] == "Another document" and remote.writes == 1
        assert len(await service.list()) == 1
    asyncio.run(scenario())


def test_pending_receipt_can_be_reconciled_after_source_note_changes():
    async def scenario():
        store, remote = FakeDbGateway(), Remote()
        connections = BrainConnections(store, SecretBox(Fernet.generate_key().decode()))
        destination = await connections.save("personal", "alice", ConnectionInput(
            label="Mine", endpoint="https://vault.lan", api_key="key", allow_write=True))
        notes = NotesService(store, "alice")
        note = await notes.create("Procedure", "Old steps")
        service = Promotions(store, connections, remote, "alice", publish=False)
        body = PublicationInput(source_hash=note_hash(note), source_revision=note.updated_at,
            scope="personal", destination_revision=1, generation=destination["generation"],
            path="Inbox/Reserved.md", draft="# Procedure\nOld steps", idempotency_key="unknown-write")
        remote.fail_after_write = True
        with pytest.raises(BrainError):
            await service.publish(note.id, body)
        key = (await service.list())[0]["id"]
        await notes.update(note.id, "Procedure", "New steps")
        result = await service.reconcile(key)
        assert result["status"] == "published" and remote.writes == 1
        assert (await service.list())[0]["source_changed"]
    asyncio.run(scenario())
