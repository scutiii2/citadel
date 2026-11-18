"""What a share link may show of a chat. Stronghold (`apps/stronghold/src/shares`) keeps the links.

The rules that keep a link safe about the chat itself live here, not in the browser:

* What is shared is a copy taken at that moment, cut down to the questions
  the user typed and the assistant's plain answers. Tool steps and results,
  usage data, summaries, raw logs, slash-command results, error texts and the
  text of attached files never leave.
* Deleting a chat revokes its links first, inside Stronghold, so a deleted chat never keeps a working link.
"""

from __future__ import annotations

import re

from src.services.chat_service import ChatMessage

# A question's attached files travel inside its text (see the chat views).
_ATTACHMENT = re.compile(r'\[\[ATTACHMENT filename="([^"]*)"[^\]]*\]\]\n[\s\S]*?\n\[\[/ATTACHMENT\]\]')
# A tool's download marker points at a file on the server side.
_DOWNLOAD = re.compile(r"\[\[DOWNLOAD [^\]]*\]\]")
# How a failed answer is saved (turns.py): provider and network errors are not for outsiders.
_ERROR_PREFIXES = ("error:", "⚠️ Interrupted:")


class NothingToShare(Exception):
    """The chat has no question or answer that may be shared."""


def snapshot_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """What a shared chat shows: the typed questions and the assistant's plain
    answers, as {role, content} only. See the module docstring for what is left out."""
    shared: list[ChatMessage] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if message.get("kind") or role not in ("user", "assistant") or not isinstance(content, str):
            continue
        if role == "assistant":
            if content.lstrip().startswith(_ERROR_PREFIXES):
                continue
            content = _DOWNLOAD.sub("", content).strip()
        else:
            content = _ATTACHMENT.sub(lambda m: f"📎 {m.group(1)}", content).strip()
        if content:
            shared.append({"role": role, "content": content})
    return shared
