"""The frames exchanged with ember_api (spec: Wire protocol). Frames from the server are parsed
into small values; frames for the server are plain dicts, clipped to the server's limits."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.events import HistoryLine, TurnRequest

DELTA_MAX = 20_000
NAME_MAX = 80
SUMMARY_MAX = 500
PLAN_MAX = 80
VERSION_MAX = 40
DONE_MAX = 200_000
ERROR_MAX = 2_000


@dataclass(frozen=True)
class ReadyFrame:
    worker_id: int


@dataclass(frozen=True)
class PermissionReply:
    request_id: str
    allow: bool


@dataclass(frozen=True)
class CancelFrame:
    turn_id: str


ServerFrame = TurnRequest | ReadyFrame | PermissionReply | CancelFrame


def parse_server_frame(raw: str) -> ServerFrame | None:
    """The frame in `raw`, or None for anything malformed or unknown (those are ignored)."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        kind = data.get("type")
        if kind == "ready":
            return ReadyFrame(worker_id=int(data["worker_id"]))
        if kind == "turn":
            history = tuple(HistoryLine(str(line["sender"]), str(line["text"])) for line in data.get("history", []))
            return TurnRequest(
                turn_id=str(data["turn_id"]),
                group_id=int(data["group_id"]),
                folder=str(data["folder"]),
                mode=str(data["mode"]),
                prompt=str(data["prompt"]),
                history=history,
            )
        if kind == "permission_reply":
            if not isinstance(data["allow"], bool):
                return None
            return PermissionReply(request_id=str(data["request_id"]), allow=data["allow"])
        if kind == "cancel":
            return CancelFrame(turn_id=str(data["turn_id"]))
    except (KeyError, TypeError, ValueError):
        return None
    return None


def hello_frame(plan: str | None, version: str) -> dict:
    return {"type": "hello", "plan": plan[:PLAN_MAX] if plan else None, "version": version[:VERSION_MAX]}


def heartbeat_frame() -> dict:
    return {"type": "heartbeat"}


def delta_frames(turn_id: str, text: str) -> list[dict]:
    return [
        {"type": "delta", "turn_id": turn_id, "text": text[start : start + DELTA_MAX]}
        for start in range(0, len(text), DELTA_MAX)
    ]


def tool_frame(turn_id: str, name: str, summary: str) -> dict:
    return {"type": "tool", "turn_id": turn_id, "name": name[:NAME_MAX], "summary": summary[:SUMMARY_MAX]}


def permission_request_frame(turn_id: str, request_id: str, tool: str, summary: str) -> dict:
    return {
        "type": "permission_request",
        "turn_id": turn_id,
        "request_id": request_id,
        "tool": tool[:NAME_MAX],
        "summary": summary[:SUMMARY_MAX],
    }


def usage_frame(turn_id: str, input_tokens: int, output_tokens: int) -> dict:
    return {"type": "usage", "turn_id": turn_id, "input_tokens": input_tokens, "output_tokens": output_tokens}


def turn_done_frame(turn_id: str, text: str) -> dict:
    return {"type": "turn_done", "turn_id": turn_id, "text": text[:DONE_MAX]}


def turn_error_frame(turn_id: str, message: str) -> dict:
    return {"type": "turn_error", "turn_id": turn_id, "message": message[:ERROR_MAX]}
