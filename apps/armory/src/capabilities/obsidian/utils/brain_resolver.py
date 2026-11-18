"""Resolve authorized vault snapshots. Shared credentials stay in Armory."""
import asyncio
import json
import sqlite3

import httpx

from src.capabilities.obsidian.utils.gateway import ObsidianGateway, ObsidianGatewayError
from src.capabilities.obsidian.utils.instance_brain import InstanceBrainStore
from src.citadel_auth import requester_header, service_client
from src.config import settings
from src.service_catalog import catalog
from src.services import identity_context
from src.services.service_auth import keyring

instance_store: InstanceBrainStore | None = None


def resolve(scope: str, operation: str, uid: str | None = None) -> dict:
    uid = uid if uid is not None else identity_context.current_uid()
    if scope not in {"instance", "personal"} or not uid or uid != identity_context.current_uid():
        raise ObsidianGatewayError("Brain access requires a signed-in user and configured internal authentication.")
    constrained = identity_context._from_request_meta("brain_scope")
    if operation in {"write", "append"} and constrained in {"personal", "instance"} and scope != constrained:
        raise ObsidianGatewayError("The selected auto-save destination cannot be changed by the model.")
    try:
        return asyncio.run(_resolve(scope, operation))
    except (KeyError, OSError, ValueError, sqlite3.Error):
        raise ObsidianGatewayError("Brain connection is unavailable or access was refused. Check your destination and permissions.") from None


async def authorize_management() -> None:
    try:
        await _resolve("instance", "manage")
    except (KeyError, OSError, ValueError):
        raise ObsidianGatewayError("Could not verify Instance Brain management access", status=503) from None


async def _resolve(scope: str, operation: str) -> dict:
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
        if scope == "instance":
            if result.get("authorized") is not True:
                raise ValueError("missing instance authorization")
            if operation != "manage":
                if instance_store is None:
                    raise ValueError("missing instance connection store")
                return await asyncio.to_thread(instance_store.snapshot, write=operation in {"write", "append"})
        return result
    except httpx.HTTPStatusError as error:
        if operation == "manage" and error.response.status_code == 403:
            raise ObsidianGatewayError("Instance Brain management permission is required", status=403) from None
        raise ValueError("brain connection unavailable") from None
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
