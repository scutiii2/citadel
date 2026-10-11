"""Game ownership comes from bearer sessions; the internal token is outgoing only."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import dotenv_values
from fastapi import Header, HTTPException, Request
from src.seed import seed_from_example
from src.sessions import GameSessions

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_token(path: Path | None = None) -> str:
    """INTERNAL_API_TOKEN from the environment, else from .env
    (seeded from its .example on first run). "" = not configured."""
    if path is None:
        path = ENV_PATH
        seed_from_example(path)
    return os.getenv("INTERNAL_API_TOKEN") or dotenv_values(path).get("INTERNAL_API_TOKEN") or ""


class BearerAuthentication:
    def __init__(self, sessions: GameSessions) -> None:
        self._sessions = sessions

    def owner(self, authorization: str) -> str:
        scheme, separator, token = authorization.partition(" ")
        owner = self._sessions.owner_of(token) if separator and scheme.lower() == "bearer" and token else None
        if owner is None:
            raise HTTPException(401, "Not signed in")
        return owner


async def requester(request: Request, authorization: str = Header(default="")) -> str:
    """FastAPI adapter for the app's bearer session store."""
    return BearerAuthentication(request.app.state.sessions).owner(authorization)
