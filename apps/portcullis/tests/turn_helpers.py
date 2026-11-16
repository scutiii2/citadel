"""Small helpers for Portcullis tests that start a chat turn. Stronghold runs the turn (see fake_turns.py)."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

AGENT_ID = "claude-agent"


def new_id() -> str:
    return str(uuid.uuid4())


def start(client: TestClient, chat_id: str, question: str = "hi there", **extra):
    return client.post(f"/api/chats/{chat_id}/turns", json={"question": question, "agent_id": AGENT_ID, **extra})


def events(client: TestClient, chat_id: str, after: int = 0) -> list[dict]:
    with client.stream("GET", f"/api/chats/{chat_id}/events", params={"after": after}) as response:
        assert response.status_code == 200, response.read()
        body = b"".join(response.iter_bytes()).decode()
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def chat(client: TestClient, chat_id: str) -> dict:
    return client.get(f"/api/chats/{chat_id}").json()
