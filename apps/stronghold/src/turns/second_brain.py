"""Auto-save to the second brain: the per-turn request that asks the agent to write a summary.

The agent writes through its ordinary tool loop, so tool approvals, filtering and Armory's allow_write
guard still apply. No browser-supplied path or credentials. Whether auto-save is allowed at all
(permissions, Obsidian capability, brain connection) is checked by Portcullis, which sends the answer.
"""
from __future__ import annotations

import json
import re


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
