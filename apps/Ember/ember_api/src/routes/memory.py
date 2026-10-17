"""The signed-in account's assistant memory. Distinct from private Notes."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, Field, field_validator

from src.deps import get_log_writer, require_permission
from src.models import Account
from src.services.log_service import LogWriter
from src.services.memory import MemoryClient, MemoryError, MemoryNote
from src.services.permissions import CHAT_USE

router = APIRouter(prefix="/api/memory", tags=["memory"])
require_chat = require_permission(CHAT_USE)
NoteId = Annotated[int, Path(gt=0)]


class MemoryBody(BaseModel):
    text: str = Field(min_length=1, max_length=500)

    @field_validator("text")
    @classmethod
    def clean_text(cls, text: str) -> str:
        clean = " ".join(text.split())
        if not clean:
            raise ValueError("Memory cannot be empty")
        return clean


class MemoryUpdate(MemoryBody):
    expected_text: str = Field(min_length=1, max_length=500)


def get_memory(request: Request) -> MemoryClient:
    return request.app.state.memory


async def _request(memory: MemoryClient, method: str, account: Account,
                   note_id: int | None = None, body: dict | None = None):
    try:
        return await memory.request(method, account.uid, note_id, body)
    except MemoryError as error:
        raise HTTPException(error.status, str(error)) from error


@router.get("", response_model=list[MemoryNote])
async def list_memories(account: Account = Depends(require_chat), memory: MemoryClient = Depends(get_memory)):
    return await _request(memory, "GET", account)


@router.post("", response_model=MemoryNote, status_code=201)
async def create_memory(body: MemoryBody, account: Account = Depends(require_chat),
                        memory: MemoryClient = Depends(get_memory), logs: LogWriter = Depends(get_log_writer)):
    note = await _request(memory, "POST", account, body=body.model_dump())
    await logs.action(account, "memory.create", "Saved a memory")
    return note


@router.put("/{note_id}", response_model=MemoryNote)
async def update_memory(note_id: NoteId, body: MemoryUpdate, account: Account = Depends(require_chat),
                        memory: MemoryClient = Depends(get_memory), logs: LogWriter = Depends(get_log_writer)):
    note = await _request(memory, "PUT", account, note_id, body.model_dump())
    await logs.action(account, "memory.update", "Edited a memory")
    return note


@router.delete("/{note_id}", status_code=204)
async def delete_memory(note_id: NoteId, account: Account = Depends(require_chat),
                        memory: MemoryClient = Depends(get_memory), logs: LogWriter = Depends(get_log_writer)):
    await _request(memory, "DELETE", account, note_id)
    await logs.action(account, "memory.delete", "Deleted a memory")
    return Response(status_code=204)
