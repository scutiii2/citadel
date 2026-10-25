"""Resolve current authorized snapshots in Ember; secrets live only in request objects."""
import json
import urllib.error
import urllib.request

from src.config import settings
from src.services import identity_context
from src.capabilities.obsidian.utils.gateway import ObsidianGateway, ObsidianGatewayError, _NoRedirect


def resolve(scope: str, operation: str, uid: str | None = None) -> dict:
    uid = uid if uid is not None else identity_context.current_uid()
    if scope not in {"instance", "personal"} or not settings.internal_api_token or not uid:
        raise ObsidianGatewayError("Brain access requires a signed-in user and configured internal authentication.")
    constrained = identity_context._from_request_meta("brain_scope")
    if operation in {"write", "append"} and constrained in {"personal", "instance"} and scope != constrained:
        raise ObsidianGatewayError("The selected auto-save destination cannot be changed by the model.")
    request = urllib.request.Request(settings.ember_api_url.rstrip("/") + "/api/brains/internal/resolve",
        data=json.dumps({"scope": scope, "operation": operation}).encode(), method="POST",
        headers={"X-Internal-Token": settings.internal_api_token, "X-Requester-Uid": uid, "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=5) as response:
            raw = response.read(32_001)
            if len(raw) > 32_000:
                raise ValueError()
            result = json.loads(raw)
            if not isinstance(result, dict) or result.get("scope") != scope:
                raise ValueError()
            return result
    except (OSError, ValueError):
        raise ObsidianGatewayError("Brain connection is unavailable or access was refused. Check your destination and permissions.") from None


def gateway(snapshot: dict) -> ObsidianGateway:
    if snapshot["source"] == "legacy":
        return ObsidianGateway(settings.obsidian_base_url, settings.obsidian_api_key,
            timeout=settings.obsidian_timeout, verify_tls=settings.obsidian_verify_tls,
            allow_write=settings.obsidian_allow_write)
    return ObsidianGateway(snapshot["endpoint"], snapshot["api_key"], timeout=settings.obsidian_timeout,
        verify_tls=True, allow_write=snapshot["allow_write"], personal=snapshot["scope"] == "personal")
