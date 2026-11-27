"""The stored files a chat mentions: what its holds are taken on."""

from __future__ import annotations

import json
import re
from typing import Any

_FILE_ID = re.compile(r"f_[0-9a-f]{32}")
# Their results name every file the account has; counting them would keep all of them with one chat.
# shortcut: a batch step that lists files still counts; filter its rows too if that keeps too much.
_LISTINGS = ("tool_files_list", "tool_pdf_listFiles", "tool_media_listFiles", "tool_media_packages")


def file_ids(messages: list[dict[str, Any]]) -> list[str]:
    """Every file id the messages mention, sorted."""
    found: set[str] = set()
    for message in messages:
        parts: list[Any] = [{k: v for k, v in message.items() if k != "steps"}]
        steps = message.get("steps")
        for step in steps if isinstance(steps, list) else []:
            if isinstance(step, dict) and str(step.get("tool", "")).endswith(_LISTINGS):
                step = {k: v for k, v in step.items() if k != "result"}
            parts.append(step)
        found.update(_FILE_ID.findall(json.dumps(parts, ensure_ascii=False)))
    return sorted(found)
