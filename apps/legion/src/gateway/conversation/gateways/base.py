"""What every adapter shares: capabilities, the HTTP client, and the safe mapping of failures."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx

from src.gateway.conversation.contract import ChatRequest, ChatResult
from src.gateway.conversation.errors import GatewayError
from src.gateway.conversation.failure import SECRET_KEYS, scrub, upstream_error

CAPABILITIES = ("streams", "images", "tools", "reasoning", "schema", "audio")


class BaseGateway:
    provider = ""
    defaults = {name: name != "audio" for name in CAPABILITIES}
    forwards_images = False  # True: the upstream service decides about images, so the gateway does not pre-refuse them

    def __init__(self, gateway_id: str, entry: dict[str, Any], transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.id, self.entry = gateway_id, entry
        self.model = str(entry.get("model", ""))
        self.timeout = float(entry.get("timeout_s", 300))
        self.capabilities = {**self.defaults, **{k: bool(v) for k, v in (entry.get("capabilities") or {}).items() if k in self.defaults}}
        if not self.sends_audio(entry):
            self.capabilities["audio"] = False  # the switch cannot add what the adapter cannot send
        self.secrets = [str(entry[k]) for k in SECRET_KEYS if entry.get(k)]
        self.http = httpx.AsyncClient(transport=transport, follow_redirects=False, timeout=self.timeout)

    async def aclose(self) -> None:
        """Release both SDK and service connection pools."""
        client = getattr(self, "client", None)
        if client is not None:
            await client.close()
        await self.http.aclose()

    def sends_audio(self, entry: dict[str, Any]) -> bool:
        """Whether this adapter has a way to put audio in a request."""
        return False

    def can(self, capability: str) -> bool:
        return self.capabilities[capability]

    def validate(self, request: ChatRequest) -> None:
        """Adapter-specific refusals (raise GatewayError 422). Capabilities are checked by the service."""

    def error_from(self, error: Exception) -> GatewayError:
        status = getattr(error, "status_code", None)
        if status is None:
            if "Timeout" in type(error).__name__:
                return GatewayError(504, "gateway_timeout", "The model service took too long to answer.", kind="unavailable")
            if isinstance(error, (httpx.HTTPError, ConnectionError)) or "Connection" in type(error).__name__:
                reason = scrub(str(error.__cause__ or ""), self.secrets, 160)
                return GatewayError(502, "gateway_unreachable", f"The model service could not be reached{f' ({reason})' if reason else ''}. Check the address and port.", kind="unavailable")
            return GatewayError(502, "gateway_bad_reply", f"The model service sent an unusable reply ({type(error).__name__}). The address may not be an API.", kind="unavailable")
        headers = getattr(getattr(error, "response", None), "headers", None) or {}
        return upstream_error(status, getattr(error, "message", None) or str(error), headers.get("retry-after"), self.secrets)

    @asynccontextmanager
    async def guard(self) -> AsyncIterator[None]:
        """Turns any failure inside the block into a GatewayError whose text holds no secret."""
        try:
            yield
        except GatewayError:
            raise
        except Exception as error:
            raise self.error_from(error) from None

    async def complete(self, request: ChatRequest) -> ChatResult:
        raise NotImplementedError

    def stream(self, request: ChatRequest) -> AsyncIterator[tuple]:
        raise NotImplementedError

    async def probe(self) -> str:
        raise NotImplementedError

    async def models(self) -> list[str]:
        """The model names the provider lists for this key. Services and providers without a list refuse."""
        raise GatewayError(422, "models_unsupported", f"The gateway '{self.id}' has no model list.")


def truncated(name: str = "The model service") -> GatewayError:
    return GatewayError(502, "gateway_bad_reply", f"{name} ended its reply before completion.", kind="unavailable")
