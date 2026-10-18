"""The frames exchanged with a worker (spec: Wire protocol). Frames from a worker are
validated here; frames for a worker are plain dicts built by the helpers below."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

PROVIDERS = ("claude", "codex")
MODES = ("ask", "accept_edits", "plan", "full_auto")


class Hello(BaseModel):
    type: Literal["hello"] = "hello"
    plan: str | None = Field(default=None, max_length=80)
    version: str = Field(default="", max_length=40)


class Heartbeat(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"


class Delta(BaseModel):
    type: Literal["delta"] = "delta"
    turn_id: str = Field(max_length=64)
    text: str = Field(max_length=20_000)


class ToolUsed(BaseModel):
    type: Literal["tool"] = "tool"
    turn_id: str = Field(max_length=64)
    name: str = Field(max_length=80)
    summary: str = Field(default="", max_length=500)


class PermissionRequested(BaseModel):
    type: Literal["permission_request"] = "permission_request"
    turn_id: str = Field(max_length=64)
    request_id: str = Field(max_length=64)
    tool: str = Field(max_length=80)
    summary: str = Field(default="", max_length=500)


class Usage(BaseModel):
    type: Literal["usage"] = "usage"
    turn_id: str = Field(max_length=64)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class TurnDone(BaseModel):
    type: Literal["turn_done"] = "turn_done"
    turn_id: str = Field(max_length=64)
    text: str = Field(max_length=200_000)


class TurnError(BaseModel):
    type: Literal["turn_error"] = "turn_error"
    turn_id: str = Field(max_length=64)
    message: str = Field(max_length=2_000)


class BrowseResult(BaseModel):
    """The folder the user picked in the dialog the worker opened, or None when it was cancelled."""

    type: Literal["browse_result"] = "browse_result"
    request_id: str = Field(max_length=64)
    path: str | None = Field(default=None, max_length=500)


WorkerFrame = Union[Hello, Heartbeat, Delta, ToolUsed, PermissionRequested, Usage, TurnDone, TurnError, BrowseResult]
_FRAMES: TypeAdapter[WorkerFrame] = TypeAdapter(Annotated[WorkerFrame, Field(discriminator="type")])


def parse_worker_frame(raw: str) -> WorkerFrame | None:
    """The frame in `raw`, or None for anything malformed or of an unknown type (those are ignored)."""
    try:
        return _FRAMES.validate_json(raw)
    except ValidationError:
        return None


def ready_frame(worker_id: int) -> dict:
    return {"type": "ready", "worker_id": worker_id}


def turn_frame(*, turn_id: str, group_id: int, folder: str, mode: str, prompt: str, history: list[dict]) -> dict:
    return {
        "type": "turn",
        "turn_id": turn_id,
        "group_id": group_id,
        "folder": folder,
        "mode": mode,
        "prompt": prompt,
        "history": history,
    }


def permission_reply_frame(request_id: str, allow: bool) -> dict:
    return {"type": "permission_reply", "request_id": request_id, "allow": allow}


def browse_frame(request_id: str, start: str | None) -> dict:
    """Asks the worker to open a folder dialog on its computer, starting at `start`."""
    return {"type": "browse", "request_id": request_id, "start": start}


def cancel_frame(turn_id: str) -> dict:
    return {"type": "cancel", "turn_id": turn_id}
