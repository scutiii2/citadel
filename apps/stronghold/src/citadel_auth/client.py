"""Fresh service assertions on every HTTP request, including persistent MCP."""

import httpx

from .requester import current_requester_token
from .tokens import sign_assertion


class ServiceAuth(httpx.Auth):
    """Reuse loaded private key, never a replayable JWT."""

    def __init__(self, keyring, audience: str):
        self.keyring, self.audience = keyring, audience

    async def async_auth_flow(self, request):
        await self.keyring.ensure_identity()
        request.headers["Authorization"] = "Bearer " + sign_assertion(self.keyring, self.audience)
        yield request

    def auth_flow(self, request):
        """Support already-initialized synchronous clients without filesystem I/O."""
        request.headers["Authorization"] = "Bearer " + sign_assertion(self.keyring, self.audience)
        yield request


def service_client(keyring, audience: str, **httpx_kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(auth=ServiceAuth(keyring, audience), **httpx_kwargs)


def requester_header(token: str | None = None) -> dict[str, str]:
    token = current_requester_token() if token is None else token
    return {"X-Citadel-Requester": token} if token else {}


def requester_meta(token: str | None = None) -> dict[str, str]:
    token = current_requester_token() if token is None else token
    return {"requester_token": token} if token else {}
