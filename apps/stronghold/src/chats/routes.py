"""/chats and /chat-folders: an account's chat history, folders and search.

Portcullis serves these as /api/chats and /api/chat-folders (chat.use) and runs the answers
themselves: it saves a question, asks the agent, and saves the answer here. It tells Stronghold
which of the account's chats have an answer being written when a folder is deleted.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.chats.store import (
    MAX_QUERY_CHARS,
    MIN_QUERY_CHARS,
    TITLE_MAX,
    ChatLimitError,
    ChatNotFound,
    ChatStore,
    FolderBusy,
    FolderLimitError,
    FolderNameTaken,
    FolderNotFound,
    NotABranchPoint,
)
from src.platform import PortcullisClient
from src.requester import Requester, current_requester

router = APIRouter(prefix="/chats", tags=["chats"])
folder_router = APIRouter(prefix="/chat-folders", tags=["chat-folders"])

ChatId = Path(pattern=r"^[A-Za-z0-9-]{8,64}$")
FolderId = Path(ge=1, le=2**31 - 1)
NAME_MAX = 60


def get_chats(request: Request) -> ChatStore:
    return request.app.state.chats


def get_platform(request: Request) -> PortcullisClient:
    return request.app.state.platform


class Message(BaseModel):
    """A chat message as Portcullis saved it: a role and text, plus whatever it records about the answer."""

    model_config = ConfigDict(extra="allow")
    role: Literal["user", "assistant"]
    content: str


def _clean(text: str, what: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        raise ValueError(f"{what} must not be blank")
    return cleaned


class PutBody(BaseModel):
    title: str = Field(max_length=TITLE_MAX)
    agent_id: str | None = Field(default=None, max_length=120)
    messages: list[Message]

    @field_validator("title")
    @classmethod
    def clean_title(cls, title: str) -> str:
        return _clean(title, "title")


class MessagesBody(BaseModel):
    messages: list[Message]
    agent_id: str | None = Field(default=None, max_length=120)


class UpdateBody(BaseModel):
    title: str | None = Field(default=None, max_length=TITLE_MAX)
    folder_id: int | None = None
    pinned: bool | None = None
    save_to_second_brain: bool | None = None
    second_brain_scope: Literal["instance", "personal"] | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, title: str | None) -> str | None:
        return None if title is None else _clean(title, "title")

    @model_validator(mode="after")
    def something_to_change(self) -> UpdateBody:
        if (self.title is None and self.pinned is None and self.save_to_second_brain is None
                and self.second_brain_scope is None and "folder_id" not in self.model_fields_set):
            raise ValueError("send a title, a folder_id, pinned or save_to_second_brain")
        return self


class BranchBody(BaseModel):
    upto: int = Field(ge=0)


def _messages(items: list[Message]) -> list[dict[str, Any]]:
    return [m.model_dump(exclude_none=True) for m in items]


def _chat_gone() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")


# --- chats -----------------------------------------------------------------------------------


@router.get("")
async def list_chats(who: Requester = Depends(current_requester), chats: ChatStore = Depends(get_chats)) -> list[dict]:
    """Newest first, without transcripts."""
    return await chats.list(who.uid)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_chats(who: Requester = Depends(current_requester), chats: ChatStore = Depends(get_chats)) -> Response:
    """Every chat of the account, after revoking their share links."""
    await chats.delete_all(who.uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/search")
async def search_chats(q: str = Query(min_length=MIN_QUERY_CHARS, max_length=MAX_QUERY_CHARS),
                       who: Requester = Depends(current_requester), chats: ChatStore = Depends(get_chats)) -> list[dict]:
    """Chats whose title or messages contain `q`, newest first, at most 50, with a snippet around the first match."""
    return await chats.search(who.uid, q)


@router.delete("/accounts/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_account(uid: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
                        chats: ChatStore = Depends(get_chats)) -> Response:
    """Chats, transcripts and folders of a deleted account. Portcullis calls it when an administrator deletes it."""
    await chats.purge_owner(uid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{chat_id}")
async def get_chat(chat_id: str = ChatId, who: Requester = Depends(current_requester),
                   chats: ChatStore = Depends(get_chats)) -> dict:
    try:
        return await chats.get(who.uid, chat_id)
    except ChatNotFound as error:
        raise _chat_gone() from error


@router.put("/{chat_id}")
async def put_chat(body: PutBody, chat_id: str = ChatId, who: Requester = Depends(current_requester),
                   chats: ChatStore = Depends(get_chats)) -> dict:
    """Creates the chat or replaces its title, agent and transcript."""
    try:
        return await chats.put(who.uid, chat_id, body.title, body.agent_id, _messages(body.messages))
    except ChatLimitError as error:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(error)) from error


@router.put("/{chat_id}/messages")
async def replace_messages(body: MessagesBody, chat_id: str = ChatId, who: Requester = Depends(current_requester),
                           chats: ChatStore = Depends(get_chats)) -> dict:
    """A new transcript for an existing chat: it keeps its title, and its agent unless one is sent."""
    try:
        return await chats.replace_messages(who.uid, chat_id, _messages(body.messages), body.agent_id)
    except ChatNotFound as error:
        raise _chat_gone() from error
    except ChatLimitError as error:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(error)) from error


@router.patch("/{chat_id}")
async def update_chat(body: UpdateBody, chat_id: str = ChatId, who: Requester = Depends(current_requester),
                      chats: ChatStore = Depends(get_chats)) -> dict:
    changes = body.model_dump(exclude_unset=True)
    try:
        return await chats.update(who.uid, chat_id, changes)
    except ChatNotFound as error:
        raise _chat_gone() from error
    except FolderNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found") from error


@router.post("/{chat_id}/branch", status_code=status.HTTP_201_CREATED)
async def branch_chat(body: BranchBody, chat_id: str = ChatId, who: Requester = Depends(current_requester),
                      chats: ChatStore = Depends(get_chats)) -> dict:
    """A copy up to and including the answer at `upto`, as a new chat."""
    try:
        return await chats.branch(who.uid, chat_id, body.upto)
    except ChatNotFound as error:
        raise _chat_gone() from error
    except NotABranchPoint as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "A branch can only end on one of the assistant's answers") from error
    except ChatLimitError as error:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(error)) from error


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: str = ChatId, who: Requester = Depends(current_requester),
                      chats: ChatStore = Depends(get_chats)) -> Response:
    """The chat and its share links."""
    try:
        await chats.delete(who.uid, chat_id)
    except ChatNotFound as error:
        raise _chat_gone() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- folders ---------------------------------------------------------------------------------


class CreateFolderBody(BaseModel):
    name: str = Field(max_length=NAME_MAX)

    @field_validator("name")
    @classmethod
    def clean_name(cls, name: str) -> str:
        return _clean(name, "name")


class UpdateFolderBody(BaseModel):
    name: str | None = Field(default=None, max_length=NAME_MAX)
    position: int | None = Field(default=None, ge=0, le=100_000)
    direction: Literal["up", "down"] | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, name: str | None) -> str | None:
        return None if name is None else _clean(name, "name")

    @model_validator(mode="after")
    def something_to_change(self) -> UpdateFolderBody:
        if self.name is None and self.position is None and self.direction is None:
            raise ValueError("send a name, a position or a direction")
        if self.direction is not None and (self.name is not None or self.position is not None):
            raise ValueError("send direction on its own")
        return self


class DeleteFolderBody(BaseModel):
    # This account's chats that have an answer being written (Portcullis runs the answers).
    running: list[str] = Field(default_factory=list, max_length=1000)


def _folder_out(doc: dict[str, Any], chat_count: int) -> dict[str, Any]:
    return {"id": doc["id"], "name": doc["name"], "position": doc["position"], "chat_count": chat_count}


def _folder_gone() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Folder not found")


def _conflict(error: Exception) -> HTTPException:
    if isinstance(error, FolderLimitError):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    return HTTPException(status.HTTP_409_CONFLICT, "A folder with that name already exists")


@folder_router.get("")
async def list_folders(who: Requester = Depends(current_requester), chats: ChatStore = Depends(get_chats)) -> list[dict]:
    return await chats.folders(who.uid)


@folder_router.post("", status_code=status.HTTP_201_CREATED)
async def create_folder(body: CreateFolderBody, who: Requester = Depends(current_requester),
                        chats: ChatStore = Depends(get_chats), platform: PortcullisClient = Depends(get_platform)) -> dict:
    try:
        folder = await chats.create_folder(who.uid, body.name)
    except (FolderLimitError, FolderNameTaken) as error:
        raise _conflict(error) from error
    await platform.log_action(who.uid, "chat_folder.create", f'Created folder "{folder["name"]}"')
    return folder


@folder_router.patch("/{folder_id}")
async def update_folder(body: UpdateFolderBody, folder_id: int = FolderId, who: Requester = Depends(current_requester),
                        chats: ChatStore = Depends(get_chats), platform: PortcullisClient = Depends(get_platform)) -> dict:
    try:
        if body.name is not None:
            folder = await chats.rename_folder(who.uid, folder_id, body.name)
            await platform.log_action(who.uid, "chat_folder.rename", f'Renamed a folder to "{folder["name"]}"')
        if body.position is not None:
            folder = await chats.reorder_folder(who.uid, folder_id, body.position)
        if body.direction is not None:
            folder = await chats.move_folder(who.uid, folder_id, body.direction)
            await platform.log_action(who.uid, "chat_folder.move", f'Moved folder "{folder["name"]}" {body.direction}')
    except FolderNotFound as error:
        raise _folder_gone() from error
    except FolderNameTaken as error:
        raise _conflict(error) from error
    return _folder_out(folder, await chats.count_in_folder(who.uid, folder_id))


@folder_router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(body: DeleteFolderBody | None = None, folder_id: int = FolderId,
                        who: Requester = Depends(current_requester), chats: ChatStore = Depends(get_chats),
                        platform: PortcullisClient = Depends(get_platform)) -> Response:
    """The folder and every chat in it, after revoking their share links. Refused while one of those chats
    has an answer being written, so a live answer is never cut off."""
    try:
        name, chat_count = await chats.delete_folder(who.uid, folder_id, set(body.running if body else []))
    except FolderNotFound as error:
        raise _folder_gone() from error
    except FolderBusy as error:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "A chat in this folder is still writing an answer. Wait for it to finish.") from error
    await platform.log_action(who.uid, "chat_folder.delete", f'Deleted folder "{name}" and its {chat_count} chat(s)')
    return Response(status_code=status.HTTP_204_NO_CONTENT)
