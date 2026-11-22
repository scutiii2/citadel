"""The Legion and Stronghold ask routes, opened only by an outside client's key.

No login, cookie or account token reaches it, and the key opens nothing else. Every check that
cannot decide refuses, and an answer whose tokens cannot be recorded is withheld."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.security import client_ip
from src.services.legion_ask import LegionUnavailable
from src.services.outside_clients import OutsideClients
from src.services.outside_guard import OutsideRefused

router = APIRouter(prefix="/api/outside")

class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=8000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


def _bearer(request: Request) -> str | None:
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    return value.strip() if scheme.lower() == "bearer" else None


def _refused(error: OutsideRefused) -> JSONResponse:
    headers = {"Retry-After": str(error.retry_after)} if error.retry_after else None
    return JSONResponse({"detail": error.message}, status_code=error.status, headers=headers)


def _unavailable(detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=503)


async def _upstream_refusal(session, clients: OutsideClients, client, ip: str, service: str) -> None:
    try:
        await clients.record(client, service=service, action="refused", reason="upstream", status=503, ip=ip)
        await session.commit()
    except Exception:  # noqa: BLE001 - the audit write never changes the refusal
        pass


@router.post("/legion/ask")
async def ask(body: AskBody, request: Request) -> JSONResponse:
    return await _ask(request, body, service="legion", memory=False)


@router.post("/stronghold/ask")
async def ask_stronghold(body: AskBody, request: Request) -> JSONResponse:
    return await _ask(request, body, service="stronghold", memory=True)


async def _ask(request: Request, body: AskBody, *, service: str, memory: bool) -> JSONResponse:
    state = request.app.state
    ip = client_ip(request)
    try:
        async with state.database.sessions() as session:
            clients = OutsideClients(session)
            try:
                client = await state.outside_guard.admit(clients, _bearer(request), service, ip)
            except OutsideRefused as error:
                try:
                    await session.commit()  # keep the refusal event
                except Exception:  # noqa: BLE001 - the audit write never changes the refusal
                    pass
                return _refused(error)
            await session.commit()

            entry = await state.agent_directory.entry()
            if entry is None:
                await _upstream_refusal(session, clients, client, ip, service)
                return _unavailable("No agent is running")
            try:
                answer = await state.legion_ask.ask(
                    entry.url, client, body.question, [t.model_dump() for t in body.history], memory=memory,
                )
            except LegionUnavailable:
                await _upstream_refusal(session, clients, client, ip, service)
                return _unavailable("Legion is unavailable")

            await clients.record(client, service=service, action="call", status=200, tokens=answer.tokens, ip=ip)
            used, _ = await clients.spent(client)
            await session.commit()
    except Exception:  # noqa: BLE001 - database down, or the tokens could not be recorded: no answer leaves
        return _unavailable("The service is unavailable")
    return JSONResponse({
        "answer": answer.text,
        "usage": {"total_tokens": answer.tokens, "budget_remaining": max(0, client.budget_tokens - used)},
        "request_id": answer.request_id,
    })
