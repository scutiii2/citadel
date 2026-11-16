"""Whether auto-save to the second brain is allowed for an account (Stronghold builds the save request)."""
from __future__ import annotations

from src.models import Account
from src.services.mcp_server_info import McpServerInfo
from src.services.permissions import TOOLS_EXECUTE
from src.services.brain_client import PUBLISH, BrainError


async def available(account: Account, info: McpServerInfo, *, scope="instance", connections=None) -> bool:
    if scope == "both":
        return await available(account, info, scope="personal", connections=connections) or await available(account, info, scope="instance", connections=connections)
    if scope == "instance" and PUBLISH not in account.permission_names:
        return False
    if TOOLS_EXECUTE not in account.permission_names:
        return False
    if connections is not None:
        try:
            await connections.resolve(scope, account.uid, write=True, publish=PUBLISH in account.permission_names)
        except BrainError:
            return False
    return any(
        row.get("name") == "obsidian" and row.get("enabled") is True
        and "tool_obsidian_write" in row.get("tools", [])
        for row in await info.capabilities(account) if isinstance(row, dict)
    )
