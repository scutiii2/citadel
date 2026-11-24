"""Whether every tool run needs approval. Armory owns the rule; this reads it for Portcullis.

A guard that cannot decide refuses: if Armory does not answer, or answers with anything but an explicit off,
approval is required. A switch stored here before Armory took the rule over is carried over once: while Armory has
never saved the switch and an old row says on, the row is sent to Armory and then dropped. A failed carry-over keeps
the row and requires approval."""

from __future__ import annotations

from src.models import Account
from src.services.mcp_server_info import McpServerInfo, McpServerRefused, McpServerUnavailable
from src.services.settings_service import SettingsService


async def forced_approval(info: McpServerInfo, settings: SettingsService, account: Account) -> bool:
    try:
        body = await info.tool_approval(account)
    except (McpServerUnavailable, McpServerRefused):
        return True
    if body.get("stored") is False:
        legacy = await settings.legacy_force_tool_approval()
        if legacy is not None:
            if legacy:
                try:
                    await info.set_tool_approval(account, True)
                except (McpServerUnavailable, McpServerRefused):
                    return True
            await settings.drop_legacy_force_tool_approval()
            return legacy
    return body.get("force_tool_approval") is not False
