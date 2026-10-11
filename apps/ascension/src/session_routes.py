"""Ticket redemption and a per-app, per-peer-IP attempt limit."""
from __future__ import annotations
import time
from collections import OrderedDict
from collections.abc import Callable
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from src.ember_identity import EmberIdentity, IdentityUnavailable
from src.sessions import GameSessions


class RedeemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=1, max_length=200)


class RedeemLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic, attempts: int = 10, window_seconds: float = 60) -> None:
        self._clock = clock
        self._attempts = attempts
        self._window_seconds = window_seconds
        self._clients: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def allow(self, address: str) -> bool:
        now = self._clock()
        while self._clients and next(iter(self._clients.values()))[0] + self._window_seconds <= now:
            self._clients.popitem(last=False)
        started, count = self._clients.get(address, (now, 0))
        if count >= self._attempts:
            return False
        self._clients[address] = (started, count + 1)
        return True


class SessionRedeemer:
    def __init__(self, sessions: GameSessions, identity: EmberIdentity | None, limiter: RedeemLimiter, dev_fake_owner: str = "") -> None:
        self._sessions = sessions
        self._identity = identity
        self._limiter = limiter
        self._dev_fake_owner = dev_fake_owner

    async def redeem(self, request: Request) -> dict:
        address = request.client.host if request.client else "unknown"
        if not self._limiter.allow(address):
            raise HTTPException(429, "Too many redeem attempts")
        try:
            body = RedeemBody.model_validate(await request.json())
        except (ValidationError, ValueError, UnicodeError) as error:
            raise HTTPException(400, "invalid request") from error
        if self._dev_fake_owner and body.ticket == "dev":
            owner = self._dev_fake_owner
        else:
            if self._identity is None:
                raise HTTPException(502, "Ember is not available")
            try:
                owner = await self._identity.redeem(body.ticket)
            except IdentityUnavailable as error:
                raise HTTPException(502, "Ember is not available") from error
        if owner is None:
            raise HTTPException(401, "Invalid ticket")
        return {"token": self._sessions.open(owner), "expires_in": self._sessions.ttl_seconds}


class SessionRoutes:
    def mount(self, app: FastAPI) -> None:
        @app.post("/session/redeem")
        async def redeem(request: Request) -> dict:
            return await SessionRedeemer(request.app.state.sessions, request.app.state.identity,
                                         request.app.state.redeem_limiter, request.app.state.dev_fake_owner).redeem(request)
