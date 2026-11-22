"""/api/commands, /api/capabilities (and /api/capabilities/{name}/gui, a
capability's page layout): mcp_server's command registry, capability help
and capability switchboard, passed through. Reading needs tools.view.
Switching a capability (going online reloads its code from disk) and
refreshing the capability list (POST /api/capabilities/refresh, which finds
folders added while mcp_server runs) need capabilities.manage. Both change
mcp_server for everyone and are written to the activity log.

The command form (tools.view) also gets a select's options from a path a
tool's schema declares (`options_url`, with {placeholders} filled from
`arg.<param>`), and can store a dropped file on mcp_server for a file-path
parameter (/api/uploads)."""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import AsyncIterator
from typing import Any, Literal
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.config import Settings
from src.deps import get_log_writer, get_server_tools, get_settings, require_any_permission, require_permission
from src.models import Account
from src.services.caller import Caller
from src.services.log_service import LogWriter
from src.services.mcp_server_info import McpServerInfo, McpServerRefused, McpServerUnavailable, is_server_path
from src.services.permissions import (TOOLS_VIEW, CAPABILITIES_MANAGE, FILES_UPLOAD, FILES_DOWNLOAD)
from src.services.server_tools import ServerTools, ServerUnavailable

router = APIRouter(prefix="/api", tags=["server-info"])

require_tools = require_any_permission(TOOLS_VIEW, CAPABILITIES_MANAGE)
require_upload = require_permission(FILES_UPLOAD)
require_download = require_permission(FILES_DOWNLOAD)
require_admin = require_permission(CAPABILITIES_MANAGE)

# Capability ids and command names as mcp_server defines them (one Path()
# per route: FastAPI binds a shared instance to the first parameter name).
NAME_PATTERN = r"^[A-Za-z0-9_.-]{1,64}$"
# A file for a command's file-path parameter (mcp_server's /upload decides
# which types it takes).
UPLOAD_MAX_BYTES = 15 * 1024 * 1024
_UPLOAD_MAX_BASE64 = (UPLOAD_MAX_BYTES + 2) // 3 * 4
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
# The `path` of a download marker: whatever mcp_server named, without control characters.
DOWNLOAD_PATH_PATTERN = r"^[^\x00-\x1f\x7f]{1,1000}$"


def get_server_info(request: Request, settings: Settings = Depends(get_settings)) -> McpServerInfo:
    return McpServerInfo(
        request.app.state.upstream, request.app.state.catalog.mcp_url(), request.app.state.keyring, request.app.state.traffic
    )


async def _call(awaitable) -> Any:
    try:
        return await awaitable
    except McpServerUnavailable as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "mcp_server is unreachable") from error
    except McpServerRefused as error:
        code = status.HTTP_404_NOT_FOUND if error.status == 404 else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, str(error)) from error


class CommandOut(BaseModel):
    capability: str
    name: str
    description: str
    tool_name: str


class CapabilityOut(BaseModel):
    name: str
    enabled: bool
    label: str | None = None
    tools: list[str] = []
    resources: list[str] = []
    # Whether the capability ships a page ember_web can draw.
    has_gui: bool = False
    # Why the capability could not be brought online (a trimmed traceback), else null.
    load_error: str | None = None
    # Its folder is gone from mcp_server's disk.
    missing: bool = False
    # Its tools were imported (true even while switched off); false for a folder only discovered.
    loaded: bool = True


class CapabilitySwitch(BaseModel):
    enabled: bool


class OptionOut(BaseModel):
    value: str
    label: str
    # Anything else the option carries, for a param's `sets` / `shows`.
    extra: dict[str, str] = {}


class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data: str = Field(min_length=1, max_length=_UPLOAD_MAX_BASE64)


class UploadOut(BaseModel):
    # Where mcp_server stored it: the value for the file-path parameter.
    path: str


@router.get("/commands")
async def list_commands(
    account: Account = Depends(require_tools), info: McpServerInfo = Depends(get_server_info)
) -> list[CommandOut]:
    """Slash commands of the enabled capabilities: /<capability> <name>."""
    rows = await _call(info.commands(account))
    return [CommandOut(**{k: str(r.get(k, "")) for k in CommandOut.model_fields}) for r in rows if isinstance(r, dict)]


@router.get("/commands/help")
async def help_index(account: Account = Depends(require_tools), info: McpServerInfo = Depends(get_server_info)) -> Any:
    """What /help shows: every enabled capability and its commands."""
    return await _call(info.help_index(account))


@router.get("/commands/help/{capability}")
async def capability_help(
    capability: str = Path(pattern=NAME_PATTERN),
    target: Literal["all", "tools", "commands", "workflow"] = Query(default="all"),
    command: str | None = Query(default=None, pattern=r"^[A-Za-z0-9_.-]{1,64}$"),
    account: Account = Depends(require_tools),
    info: McpServerInfo = Depends(get_server_info),
) -> Any:
    """What /<capability> help shows."""
    return await _call(info.help(account, capability, target, command))


@router.get("/commands/options")
async def command_options(
    request: Request,
    template: str = Query(min_length=1, max_length=500),
    account: Account = Depends(require_tools),
    info: McpServerInfo = Depends(get_server_info),
    tools: ServerTools = Depends(get_server_tools),
) -> list[OptionOut]:
    """Options for a command-form select. `template` must be an
    `options_url` some tool declares, so this can't fetch arbitrary
    mcp_server paths; each {name} in it comes from the `arg.<name>` query
    parameter (a select that depends on another one)."""
    try:
        declared = await tools.options_templates(Caller(username=account.username, email=account.email, uid=account.uid))
    except ServerUnavailable as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "mcp_server is unreachable") from error
    if template not in declared or not is_server_path(template):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown options template")
    path = template
    for name in _PLACEHOLDER.findall(template):
        value = request.query_params.get(f"arg.{name}", "")
        if not value:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"arg.{name} is required")
        if value in (".", ".."):
            # Quoting keeps a "/" out of the value, but a dot segment would still climb a level.
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"arg.{name} is not a valid value")
        path = path.replace("{" + name + "}", quote(value, safe=""))
    options = await _call(info.options(account, path))
    return [
        OptionOut(value=o["value"], label=o["label"], extra={k: v for k, v in o.items() if k not in ("value", "label")})
        for o in options
    ]


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def upload_file(
    body: UploadIn,
    account: Account = Depends(require_upload),
    info: McpServerInfo = Depends(get_server_info),
    logs: LogWriter = Depends(get_log_writer),
) -> UploadOut:
    """Stores a file on mcp_server for a command's file-path parameter
    (chat_app's command-form drop zone). Base64 in JSON, like attachments."""
    try:
        content = base64.b64decode(body.data, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "data must be base64") from error
    if len(content) > UPLOAD_MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The file is larger than 15 MB")
    filename = body.filename.replace("\\", "/").rsplit("/", 1)[-1]
    path = await _call(info.upload(account, filename, content))
    await logs.action(account, "mcp.upload", f"Uploaded '{filename}' ({len(content):,} bytes) for a command")
    return UploadOut(path=path)


_UPSTREAM_FILENAME = re.compile(r"filename\*=UTF-8''([^;]+)", re.IGNORECASE)
_FILENAME_MAX = 150


def _download_name(path: str, upstream_headers: Any) -> str:
    """The file's name: the one mcp_server gave it (its `path` is an opaque id
    that says nothing), cleaned to a bare name; else the last part of `path`."""
    match = _UPSTREAM_FILENAME.search(upstream_headers.get("content-disposition", ""))
    if match:
        name = unquote(match.group(1)).replace("\\", "/").rsplit("/", 1)[-1]
        name = "".join(c for c in name if ord(c) >= 32 and ord(c) != 127).strip()
        if name and name not in (".", ".."):
            return name[:_FILENAME_MAX]
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or "download"


@router.get("/server/download")
async def download_file(
    path: str = Query(pattern=DOWNLOAD_PATH_PATTERN),
    account: Account = Depends(require_download),
    info: McpServerInfo = Depends(get_server_info),
) -> StreamingResponse:
    """A file a tool offered with a `[[DOWNLOAD ...]]` marker, streamed from
    mcp_server. Always an attachment of an opaque type, whatever mcp_server says
    it is, so a file can never run as a page on ember's own origin."""
    upstream = await _call(info.download(account, path))
    name = _download_name(path, upstream.headers)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}", "Cache-Control": "no-store"}
    # The length is only trustworthy as long as nothing was decoded on the way.
    length = upstream.headers.get("content-length")
    if length and "content-encoding" not in upstream.headers:
        headers["Content-Length"] = length

    async def relay() -> AsyncIterator[bytes]:
        # try/finally rather than a background task: when the browser leaves
        # the generator is closed, and the upstream request still ends.
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(relay(), media_type="application/octet-stream", headers=headers)


@router.get("/capabilities")
async def list_capabilities(
    account: Account = Depends(require_tools), info: McpServerInfo = Depends(get_server_info)
) -> list[CapabilityOut]:
    # A load error is a traceback with server paths and maybe config values: admins only.
    is_admin = CAPABILITIES_MANAGE in account.permission_names
    rows = [CapabilityOut(**r) for r in await _call(info.capabilities(account)) if isinstance(r, dict)]
    if not is_admin:
        for row in rows:
            row.load_error = None
    return rows


@router.get("/capabilities/{name}/gui")
async def capability_page(
    name: str = Path(pattern=NAME_PATTERN),
    account: Account = Depends(require_tools),
    info: McpServerInfo = Depends(get_server_info),
) -> dict[str, Any]:
    """A capability's page layout, as mcp_server validated it; ember_web draws it."""
    return await _call(info.capability_page(account, name))


@router.patch("/capabilities/{name}")
async def switch_capability(
    body: CapabilitySwitch,
    name: str = Path(pattern=NAME_PATTERN),
    account: Account = Depends(require_admin),
    info: McpServerInfo = Depends(get_server_info),
    logs: LogWriter = Depends(get_log_writer),
) -> CapabilityOut:
    """Turns a capability's tools on or off for every mcp_server client
    (chat_app, ai_agent and ember alike), so admins only."""
    capability = CapabilityOut(**await _call(info.set_capability(account, name, body.enabled)))
    await logs.action(account, "mcp.capability", f"Turned capability '{name}' {'on' if body.enabled else 'off'}")
    return capability


@router.get("/armory-environment")
async def armory_environment(account: Account = Depends(require_admin), info: McpServerInfo = Depends(get_server_info)) -> Any:
    """Armory's deployment values (addresses, link keys, folders). A secret is never returned."""
    return await _call(info.environment(account))


@router.put("/armory-environment")
async def set_armory_environment(
    changes: dict[str, str | float | bool | None],
    account: Account = Depends(require_admin),
    info: McpServerInfo = Depends(get_server_info),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Armory checks and saves the change. The log names the settings, never their values."""
    result = await _call(info.set_environment(account, changes))
    await logs.action(account, "mcp.environment", f"Changed Armory settings ({', '.join(sorted(changes)) or 'none'})")
    return result


@router.get("/armory-tuning")
async def armory_tuning(account: Account = Depends(require_admin), info: McpServerInfo = Depends(get_server_info)) -> Any:
    """The caps and lifetimes of Armory's PDF and video capabilities."""
    return await _call(info.tuning(account))


@router.put("/armory-tuning/{name}")
async def set_armory_tuning(
    changes: dict[str, Any],
    name: Literal["pdf_merger", "media_downloader"],
    account: Account = Depends(require_admin),
    info: McpServerInfo = Depends(get_server_info),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Armory checks the whole result and saves it; the capability uses it from Armory's next start."""
    result = await _call(info.set_tuning(account, name, changes))
    await logs.action(account, "mcp.tuning", f"Changed {name} limits ({', '.join(sorted(changes)) or 'none'})")
    return result


@router.delete("/armory-tuning/{name}")
async def reset_armory_tuning(
    name: Literal["pdf_merger", "media_downloader"],
    account: Account = Depends(require_admin),
    info: McpServerInfo = Depends(get_server_info),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    result = await _call(info.reset_tuning(account, name))
    await logs.action(account, "mcp.tuning", f"Reset {name} limits to the defaults")
    return result


@router.get("/armory-email")
async def armory_email(account: Account = Depends(require_admin), info: McpServerInfo = Depends(get_server_info)) -> Any:
    """Armory's SMTP settings. The password is never returned."""
    return await _call(info.email_settings(account))


@router.put("/armory-email")
async def set_armory_email(
    changes: dict[str, str | int | list[str] | None],
    account: Account = Depends(require_admin),
    info: McpServerInfo = Depends(get_server_info),
    logs: LogWriter = Depends(get_log_writer),
) -> Any:
    """Armory checks the whole result and saves it. The log names the settings, never their values."""
    result = await _call(info.set_email_settings(account, changes))
    await logs.action(account, "mcp.email", f"Changed Armory email settings ({', '.join(sorted(changes)) or 'none'})")
    return result


@router.post("/capabilities/refresh")
async def refresh_capabilities(
    account: Account = Depends(require_admin),
    info: McpServerInfo = Depends(get_server_info),
    logs: LogWriter = Depends(get_log_writer),
) -> list[CapabilityOut]:
    """mcp_server looks for capability folders added while it runs; a new one
    is listed offline. Admins only, like switching."""
    capabilities = [CapabilityOut(**r) for r in await _call(info.refresh_capabilities(account)) if isinstance(r, dict)]
    await logs.action(account, "mcp.capability_refresh", "Refreshed capabilities")
    return capabilities
