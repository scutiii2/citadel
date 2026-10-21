"""Auto-save policy: server-checked capability access and a per-turn agent request.

The agent writes through its ordinary tool loop so tool approvals, filtering and
Armory's allow_write guard still apply. No browser-supplied path or credentials.
"""
from __future__ import annotations

import json
import re

from src.models import Account
from src.services.account_capability_service import AccountCapabilityService
from src.services.db_gateway import DocumentStore
from src.services.mcp_server_info import McpServerInfo
from src.services.permissions import TOOLS_EXECUTE
from src.services.brain_connections import PUBLISH, BrainError


async def available(account: Account, store: DocumentStore, info: McpServerInfo, *, scope="instance", connections=None) -> bool:
    if scope == "both":
        return await available(account, store, info, scope="personal", connections=connections) or await available(account, store, info, scope="instance", connections=connections)
    if scope == "instance" and PUBLISH not in account.permission_names:
        return False
    if TOOLS_EXECUTE not in account.permission_names:
        return False
    if connections is not None:
        try:
            await connections.resolve(scope, account.uid, write=True, publish=PUBLISH in account.permission_names)
        except BrainError:
            return False
    state = await AccountCapabilityService(store, account.uid).get()
    if "obsidian" not in state.capabilities:
        return False
    return any(
        row.get("name") == "obsidian" and row.get("enabled") is True
        and "tool_obsidian_write" in row.get("tools", [])
        for row in await info.capabilities(account) if isinstance(row, dict)
    )


def save_request(question: str, chat_id: str, request_id: str, at: str, scope: str = "instance") -> str:
    """Keep the stored question unchanged; attach this request only to the agent call."""
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:48] or "exchange"
    date = at[:10]
    path = f"Conversations/{date}-{slug}-{request_id[:8]}.md"
    frontmatter = f"---\ndate: {json.dumps(date)}\nchat_id: {json.dumps(chat_id)}\ntags: [conversation, second-brain]\n---"
    return (
        question + "\n\n[Ember per-chat preference: Save to second brain is ON]\n"
        "Answer the user's question, then save a concise summary of this exchange (question, answer, decisions and next steps) "
        f"with tool_obsidian_write at exactly {json.dumps(path)}, overwrite=false, scope={json.dumps(scope)}. "
        "Never switch to another brain if this destination is unavailable or refused. "
        "Begin the Markdown text with this frontmatter:\n" + frontmatter + "\n"
        "Use the ordinary tool approval flow; do not bypass approval or the allow_write guard. "
        "Never copy secrets. Only say the summary was saved when the tool result confirms success=true. "
        "If the write is denied or fails, keep the answer and explain that the summary was not saved."
    )
