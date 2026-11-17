"""Renew user credentials before expiry; interrupt work if renewal is refused."""

import asyncio
import time

import jwt

from src.citadel_auth import AuthError, verify_requester


class RequesterRefreshError(AuthError):
    """A turn cannot safely continue with its requester credential."""


class RequesterRenewal:
    """One mutable credential per running turn; identity remains bound to its owner."""

    def __init__(self, keyring, uid: str, token: str, refresh, *, clock=time.time):
        self.keyring, self.uid = keyring, uid
        self._token, self._refresh, self._clock = token, refresh, clock
        self._expiry = self._expires(token)

    @staticmethod
    def _expires(token: str) -> float:
        # The initial token was verified at ingress; replacement tokens are verified below.
        try:
            return float(jwt.decode(token, options={"verify_signature": False})["exp"])
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            raise RequesterRefreshError("Requester credential invalid; turn interrupted") from None

    def token(self) -> str:
        if self._clock() >= self._expiry:
            raise RequesterRefreshError("Requester token expired; turn interrupted")
        return self._token

    async def renew_if_needed(self) -> None:
        remaining = self._expiry - self._clock()
        if remaining <= 0:
            raise RequesterRefreshError("Requester token expired; turn interrupted")
        if remaining > 60:
            return
        try:
            token = await asyncio.wait_for(self._refresh(self.uid), timeout=min(15, remaining))
            who = await verify_requester(self.keyring, token, "stronghold")
            expiry = self._expires(token)
            if who.uid != self.uid or expiry <= self._clock() + 60:
                raise AuthError("invalid refreshed requester")
        except Exception:
            raise RequesterRefreshError("Requester renewal refused or unavailable; turn interrupted") from None
        self._token, self._expiry = token, expiry

    async def _maintain(self) -> None:
        while True:
            await self.renew_if_needed()
            await asyncio.sleep(max(0.01, self._expiry - self._clock() - 60))

    async def run(self, operation):
        """Supervise renewal and work together, always reaping cancelled tasks."""
        work = asyncio.create_task(operation)
        renewal = asyncio.create_task(self._maintain())
        try:
            done, _ = await asyncio.wait((work, renewal), return_when=asyncio.FIRST_COMPLETED)
            if renewal in done:
                await renewal
            return await work
        finally:
            for task in (work, renewal):
                if not task.done():
                    task.cancel()
            await asyncio.gather(work, renewal, return_exceptions=True)
