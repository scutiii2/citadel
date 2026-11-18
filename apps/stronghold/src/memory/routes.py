"""/memory: an account's assistant memory, kept by Armory. Distinct from private Notes.

Portcullis serves these as /api/memory after checking the login and the chat.use permission.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, Field, field_validator

from src.memory.client import MemoryClient, MemoryError, MemoryNote
from src.platform import PortcullisClient
from src.requester import Requester, current_requester

router = APIRouter(prefix="/memory", tags=["memory"])
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


def get_platform(request: Request) -> PortcullisClient:
    return request.app.state.platform


async def _request(memory: MemoryClient, method: str, requester: Requester,
                   note_id: int | None = None, body: dict | None = None):
    try:
        return await memory.request(method, requester.uid, note_id, body)
    except MemoryError as error:
        raise HTTPException(error.status, str(error)) from error


@router.get("", response_model=list[MemoryNote])
async def list_memories(requester: Requester = Depends(current_requester), memory: MemoryClient = Depends(get_memory)):
    return await _request(memory, "GET", requester)


@router.post("", response_model=MemoryNote, status_code=201)
async def create_memory(body: MemoryBody, requester: Requester = Depends(current_requester),
                        memory: MemoryClient = Depends(get_memory), platform: PortcullisClient = Depends(get_platform)):
    note = await _request(memory, "POST", requester, body=body.model_dump())
    # Only the fact is logged, never the text.
    await platform.log_action(requester.uid, "memory.create", "Saved a memory")
    return note


@router.put("/{note_id}", response_model=MemoryNote)
async def update_memory(note_id: NoteId, body: MemoryUpdate, requester: Requester = Depends(current_requester),
                        memory: MemoryClient = Depends(get_memory), platform: PortcullisClient = Depends(get_platform)):
    note = await _request(memory, "PUT", requester, note_id, body.model_dump())
    await platform.log_action(requester.uid, "memory.update", "Edited a memory")
    return note


@router.delete("/accounts/{uid}", status_code=204)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
                        memory: MemoryClient = Depends(get_memory)) -> Response:
    """Everything a deleted account kept. Portcullis calls it; 502 when Armory did not confirm."""
    if not await memory.purge(uid):
        raise HTTPException(502, "Memory was not purged")
    return Response(status_code=204)


@router.delete("/{note_id}", status_code=204)
async def delete_memory(note_id: NoteId, requester: Requester = Depends(current_requester),
                        memory: MemoryClient = Depends(get_memory), platform: PortcullisClient = Depends(get_platform)):
    await _request(memory, "DELETE", requester, note_id)
    await platform.log_action(requester.uid, "memory.delete", "Deleted a memory")
    return Response(status_code=204)
