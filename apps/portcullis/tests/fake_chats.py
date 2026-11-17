"""Stronghold's /chats and /chat-folders routes, simply, for Portcullis tests.

Stronghold's own tests cover the real store (apps/stronghold/tests/test_chats.py); this keeps the same
rules in a few dozen lines so Portcullis tests of chats, turns and folders run against something that
answers like it. `down` makes every call a 503.
"""

from __future__ import annotations

from tests.auth_helpers import requester, assertion

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx

MAX_CHAT_BYTES = 2 * 1024 * 1024
MAX_CHATS_PER_ACCOUNT = 1000
MAX_FOLDERS_PER_ACCOUNT = 30
_ATTACHMENT = re.compile(r"\[\[ATTACHMENT [^\]]*\]\]\n[\s\S]*?\n\[\[/ATTACHMENT\]\]")
_SPACES = re.compile(r"\s+")
_CHAT = re.compile(r"^/chats/([A-Za-z0-9-]{8,64})(/messages|/branch)?$")
_FOLDER = re.compile(r"^/chat-folders/(\d+)$")


def _answer(status: int, body: Any = None) -> httpx.Response:
    return httpx.Response(status, json=body) if body is not None else httpx.Response(status)


def _snippet(text: str, start: int, length: int) -> dict[str, Any]:
    first, end = max(0, start - 40), min(len(text), start + length + 90)
    lead = ("…" if first > 0 else "") + _SPACES.sub(" ", text[first:start])
    matched = _SPACES.sub(" ", text[start:start + length])
    after = _SPACES.sub(" ", text[start + length:end])
    return {"text": f"{lead}{matched}{after}{'…' if end < len(text) else ''}", "start": len(lead), "length": len(matched)}


@dataclass
class FakeChats:
    chats: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    folders: dict[tuple[str, int], dict[str, Any]] = field(default_factory=dict)
    down: bool = False
    # Every call, as (method, path), for tests that check what Portcullis asked.
    calls: list[tuple[str, str]] = field(default_factory=list)
    _next_folder: int = 0
    _clock: int = 0

    def _now(self) -> str:
        self._clock += 1  # strictly increasing, so "newest first" is never a tie
        return (datetime(2026, 1, 1) + timedelta(seconds=self._clock)).isoformat()

    @staticmethod
    def _details(chat: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in chat.items() if k not in ("owner", "messages")}

    def _full(self, chat: dict[str, Any]) -> dict[str, Any]:
        return {**self._details(chat), "messages": chat["messages"]}

    def _mine(self, uid: str) -> list[dict[str, Any]]:
        return [c for (owner, _), c in self.chats.items() if owner == uid]

    def respond(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        self.calls.append((method, path))
        if self.down:
            return _answer(503, {"detail": "Storage is unavailable"})
        uid = requester(request)["sub"]
        body = json.loads(request.content) if request.content else {}
        if path.startswith("/chats/accounts/") and method == "DELETE":
            owner = path.rsplit("/", 1)[-1]
            self.chats = {k: v for k, v in self.chats.items() if k[0] != owner}
            self.folders = {k: v for k, v in self.folders.items() if k[0] != owner}
            return _answer(204)
        if path.startswith("/chat-folders"):
            return self._folders(method, path, uid, body)
        if path == "/chats":
            if method == "GET":
                return _answer(200, [self._details(c) for c in sorted(self._mine(uid), key=lambda c: c["updated_at"], reverse=True)])
            for key in [k for k in self.chats if k[0] == uid]:
                del self.chats[key]
            return _answer(204)
        if path == "/chats/search":
            return _answer(200, self._search(uid, request.url.params["q"]))
        found = _CHAT.match(path)
        if found is None:
            return _answer(404, {"detail": "Not Found"})
        chat_id, sub = found.group(1), found.group(2)
        chat = self.chats.get((uid, chat_id))
        if method == "PUT" and sub is None:
            return self._put(uid, chat_id, chat, body)
        if chat is None:
            return _answer(404, {"detail": "Chat not found"})
        if method == "GET":
            return _answer(200, self._full(chat))
        if method == "DELETE":
            del self.chats[(uid, chat_id)]
            return _answer(204)
        if method == "PUT":  # /messages
            if len(json.dumps(body["messages"], ensure_ascii=False).encode()) > MAX_CHAT_BYTES:
                return _answer(413, {"detail": f"Chat is larger than {MAX_CHAT_BYTES // (1024 * 1024)} MB"})
            chat.update(messages=body["messages"], message_count=len(body["messages"]), updated_at=self._now())
            if body.get("agent_id"):
                chat["agent_id"] = body["agent_id"]
            return _answer(200, self._full(chat))
        if method == "PATCH":
            if "folder_id" in body:
                if body["folder_id"] is not None and (uid, body["folder_id"]) not in self.folders:
                    return _answer(404, {"detail": "Folder not found"})
                chat["folder_id"] = body["folder_id"]
            chat.update({k: v for k, v in body.items() if k != "folder_id" and v is not None})
            return _answer(200, self._details(chat))
        return self._branch(uid, chat, body["upto"])  # POST /branch

    def _put(self, uid: str, chat_id: str, chat: dict[str, Any] | None, body: dict[str, Any]) -> httpx.Response:
        messages = body["messages"]
        if len(json.dumps(messages, ensure_ascii=False).encode()) > MAX_CHAT_BYTES:
            return _answer(413, {"detail": f"Chat is larger than {MAX_CHAT_BYTES // (1024 * 1024)} MB"})
        now = self._now()
        if chat is None:
            if len(self._mine(uid)) + 1 > MAX_CHATS_PER_ACCOUNT:
                return _answer(413, {"detail": f"At most {MAX_CHATS_PER_ACCOUNT} chats per account - delete some first"})
            chat = self.chats[(uid, chat_id)] = {
                "owner": uid, "chat_id": chat_id, "folder_id": None, "pinned": False, "save_to_second_brain": False,
                "second_brain_scope": "instance", "created_at": now}
        chat.update(title=body["title"], agent_id=body.get("agent_id"), messages=messages,
                    message_count=len(messages), updated_at=now)
        return _answer(200, self._full(chat))

    def _branch(self, uid: str, source: dict[str, Any], upto: int) -> httpx.Response:
        messages = source["messages"]
        target = messages[upto] if 0 <= upto < len(messages) else None
        if target is None or target.get("role") != "assistant" or target.get("kind"):
            return _answer(422, {"detail": "A branch can only end on one of the assistant's answers"})
        title = f"Branch of {source['title']}"
        title = title if len(title) <= 120 else title[:119] + "…"
        if len(self._mine(uid)) + 1 > MAX_CHATS_PER_ACCOUNT:
            return _answer(413, {"detail": f"At most {MAX_CHATS_PER_ACCOUNT} chats per account - delete some first"})
        new_id, now = str(uuid.uuid4()), self._now()
        chat = self.chats[(uid, new_id)] = {
            "owner": uid, "chat_id": new_id, "title": title, "agent_id": source["agent_id"], "folder_id": source["folder_id"],
            "pinned": False, "save_to_second_brain": False, "second_brain_scope": "instance",
            "messages": messages[:upto + 1], "message_count": upto + 1, "created_at": now, "updated_at": now}
        return _answer(201, self._full(chat))

    def _search(self, uid: str, query: str) -> list[dict[str, Any]]:
        needle = query.strip()
        if len(needle) < 2:
            return []
        pattern = re.compile(re.escape(needle), re.IGNORECASE)
        hits = []
        for chat in sorted(self._mine(uid), key=lambda c: c["updated_at"], reverse=True):
            found = pattern.search(chat["title"])
            title_match = {"start": found.start(), "length": found.end() - found.start()} if found else None
            first, count = None, 0
            for index, message in enumerate(chat["messages"]):
                text = _ATTACHMENT.sub(" ", message.get("content", ""))
                found = pattern.search(text)
                if found:
                    count += 1
                    first = first or (index, _snippet(text, found.start(), found.end() - found.start()))
            if title_match or first:
                hits.append({"id": chat["chat_id"], "folder_id": chat["folder_id"], "title": chat["title"],
                             "updated_at": chat["updated_at"], "title_match": title_match,
                             "snippet": first[1] if first else None, "message_index": first[0] if first else None,
                             "message_matches": count})
        return hits[:50]

    def _folders(self, method: str, path: str, uid: str, body: dict[str, Any]) -> httpx.Response:
        mine = sorted((f for (owner, _), f in self.folders.items() if owner == uid), key=lambda f: (f["position"], f["id"]))

        def out(folder: dict[str, Any]) -> dict[str, Any]:
            count = sum(1 for c in self._mine(uid) if c["folder_id"] == folder["id"])
            return {"id": folder["id"], "name": folder["name"], "position": folder["position"], "chat_count": count}

        if path == "/chat-folders" and method == "GET":
            return _answer(200, [out(f) for f in mine])
        if path == "/chat-folders" and method == "POST":
            name = " ".join(body["name"].split())
            if len(mine) >= MAX_FOLDERS_PER_ACCOUNT:
                return _answer(409, {"detail": f"At most {MAX_FOLDERS_PER_ACCOUNT} folders per account - delete some first"})
            if any(f["name"].lower() == name.lower() for f in mine):
                return _answer(409, {"detail": "A folder with that name already exists"})
            self._next_folder += 1
            folder = self.folders[(uid, self._next_folder)] = {
                "id": self._next_folder, "name": name, "position": max((f["position"] for f in mine), default=-1) + 1}
            return _answer(201, out(folder))
        found = _FOLDER.match(path)
        folder = self.folders.get((uid, int(found.group(1)))) if found else None
        if folder is None:
            return _answer(404, {"detail": "Folder not found"})
        if method == "PATCH":
            if body.get("name") is not None:
                name = " ".join(body["name"].split())
                if any(f["id"] != folder["id"] and f["name"].lower() == name.lower() for f in mine):
                    return _answer(409, {"detail": "A folder with that name already exists"})
                folder["name"] = name
            if body.get("position") is not None:
                folder["position"] = body["position"]
            if body.get("direction"):
                index = mine.index(folder)
                target = index + (-1 if body["direction"] == "up" else 1)
                if 0 <= target < len(mine):
                    mine[index], mine[target] = mine[target], mine[index]
                    for position, item in enumerate(mine):
                        item["position"] = position
            return _answer(200, out(folder))
        inside = [c["chat_id"] for c in self._mine(uid) if c["folder_id"] == folder["id"]]
        if set(body.get("running", [])) & set(inside):
            return _answer(409, {"detail": "A chat in this folder is still writing an answer. Wait for it to finish."})
        for chat_id in inside:
            del self.chats[(uid, chat_id)]
        del self.folders[(uid, folder["id"])]
        return _answer(204)
