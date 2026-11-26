"""Stronghold's /turns routes, simply, for Portcullis tests.

Stronghold's own tests run real turns (apps/stronghold/tests/test_turns.py). This only answers what
Portcullis asks, records it, and lets a test choose the answer. `running` is what GET /turns/running says.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

_TURN = re.compile(r"^/turns/([A-Za-z0-9-]{8,64})(/[a-z]+)?$")


def chat_doc(chat_id: str, messages: list[dict[str, Any]] | None = None, **extra: Any) -> dict[str, Any]:
    doc = {"chat_id": chat_id, "title": "Chat", "agent_id": "claude-agent", "message_count": len(messages or []),
           "folder_id": None, "pinned": False,
           "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:01", **extra}
    return {**doc, "messages": messages} if messages is not None else doc


@dataclass
class FakeTurns:
    running: set[str] = field(default_factory=set)
    # Every call to /turns: (method, path, json body or None).
    calls: list[tuple[str, str, Any]] = field(default_factory=list)
    # Answers a test may change.
    start_status: int = 202
    events_status: int = 200
    events_body: bytes = b'id: 1\ndata: {"type": "final", "sequence": 1}\n\n'
    approval: dict[str, Any] = field(default_factory=lambda: {"decided": True, "decision": "allow", "tool": "send_mail"})
    approval_status: int = 200
    suggestion: str | None = "And then?"
    chat_after: dict[str, Any] = field(default_factory=lambda: chat_doc("c" * 8, [{"role": "assistant", "content": "SUMMARY"}]))
    refuse: tuple[int, str] | None = None  # (status, detail) for every call but /running

    def bodies(self, method: str, suffix: str = "") -> list[Any]:
        return [body for m, path, body in self.calls if m == method and path.endswith(suffix)]

    def respond(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else None
        self.calls.append((method, path, body))
        if path == "/turns/running":
            return httpx.Response(200, json={"chat_ids": sorted(self.running)})
        if self.refuse:
            return httpx.Response(self.refuse[0], json={"detail": self.refuse[1]})
        if method == "DELETE":
            return httpx.Response(204)
        found = _TURN.match(path)
        chat_id, action = (found.group(1), found.group(2)) if found else ("", None)
        if method == "POST" and action is None:
            if self.start_status != 202:
                return httpx.Response(self.start_status, json={"detail": "refused"})
            return httpx.Response(202, json={"chat": chat_doc(chat_id, title=(body or {}).get("title") or "Chat"), "sequence": 3})
        if action == "/events":
            if self.events_status != 200:
                return httpx.Response(self.events_status, json={"detail": "No answer is being written for this chat"})
            return httpx.Response(200, content=self.events_body, headers={"content-type": "text/event-stream"})
        if action == "/approvals":
            return httpx.Response(self.approval_status, json=self.approval)
        if action == "/questions":
            return httpx.Response(200, json={"answered": True})
        if action == "/elicitations":
            return httpx.Response(200, json={"answered": True})
        if action == "/cancel":
            return httpx.Response(200, json={"cancelled": True})
        if action == "/suggestion":
            return httpx.Response(200, json={"text": self.suggestion})
        if action in ("/summarize", "/clear"):
            return httpx.Response(200, json={**self.chat_after, "chat_id": chat_id})
        return httpx.Response(404, json={"detail": "Not found"})
