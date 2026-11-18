"""Resolve current authorized snapshots in Ember; secrets live only in request objects."""
import json
import asyncio
from src.citadel_auth import service_client, requester_header
from src.services.service_auth import keyring
import urllib.error
import urllib.request

from src.config import settings
from src.service_catalog import catalog
from src.services import identity_context
from src.capabilities.obsidian.utils.gateway import ObsidianGateway, ObsidianGatewayError, _NoRedirect


def resolve(scope: str, operation: str, uid: str | None = None) -> dict:
    uid = uid if uid is not None else identity_context.current_uid()
    if scope not in {"instance", "personal"} or not uid or uid != identity_context.current_uid():
        raise ObsidianGatewayError("Brain access requires a signed-in user and configured internal authentication.")
    constrained = identity_context._from_request_meta("brain_scope")
    if operation in {"write", "append"} and constrained in {"personal", "instance"} and scope != constrained:
        raise ObsidianGatewayError("The selected auto-save destination cannot be changed by the model.")
    try:
        return asyncio.run(_resolve(scope, operation))
    except (OSError, ValueError):
        raise ObsidianGatewayError("Brain connection is unavailable or access was refused. Check your destination and permissions.") from None


async def _resolve(scope: str, operation: str) -> dict:
    import httpx
    try:
        async with service_client(keyring, "stronghold", timeout=5) as client:
            async with client.stream("POST", catalog.url("stronghold") + "/brains/resolve",
                    json={"scope": scope, "operation": operation}, headers=requester_header()) as response:
                response.raise_for_status()
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 32_000:
                        raise ValueError("brain reply too large")
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("scope") != scope:
            raise ValueError("invalid brain reply")
        return result
    except httpx.HTTPError as error:
        if isinstance(error, httpx.ConnectError):
            catalog.refresh_soon()
        raise ValueError("brain connection unavailable") from None


def gateway(snapshot: dict) -> ObsidianGateway:
    if snapshot["source"] == "legacy":
        return ObsidianGateway(settings.obsidian_base_url, settings.obsidian_api_key,
            timeout=settings.obsidian_timeout, verify_tls=settings.obsidian_verify_tls,
            allow_write=settings.obsidian_allow_write)
    return ObsidianGateway(snapshot["endpoint"], snapshot["api_key"], timeout=settings.obsidian_timeout,
        verify_tls=True, allow_write=snapshot["allow_write"], personal=snapshot["scope"] == "personal")
