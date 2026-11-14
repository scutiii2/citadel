"""New tags for a note, written by the `tag-writer` agent: one plain light-model call.

The agent sees an excerpt of the note and the tags the account already has (so it does not
repeat them). Its reply is only a proposal: this cleans it to valid, new tags, and the user
decides. It never changes a note.
"""

from __future__ import annotations

import json
import logging
import re

from src.services.agent_directory import AgentDirectory
from src.services.agent_gateway import AgentCallError, AgentGateway, Caller
from src.services.notes import TAG_MAX

logger = logging.getLogger(__name__)

TAG_AGENT_ID = "tag-writer"
EXCERPT_MAX = 1500  # characters of title and text the model reads
KNOWN_MAX = 40  # existing tags sent to the model, most used first
MAX_NEW = 3


class TagWriterUnavailable(Exception):
    """The tag-writer agent could not be asked or did not answer."""


def tag_prompt(excerpt: str, known: list[str]) -> str:
    have = ", ".join(known[:KNOWN_MAX]) or "(none)"
    return f"Existing tags: {have}\n\nNote:\n{excerpt}\n\nJSON array of up to {MAX_NEW} new tags:"


def clean_tag(raw: object) -> str:
    """A model's tag as a valid note tag (a-z, 0-9, - and _; words joined by '-'); '' when nothing is left."""
    tag = re.sub(r"[^a-z0-9_-]+", "-", str(raw).strip().lower()).strip("-_")
    return tag[:TAG_MAX].rstrip("-_")


def parse_tags(response: str, exclude: set[str]) -> list[str]:
    """Up to MAX_NEW cleaned tags from a model's reply (a JSON array, maybe in a code fence),
    without repeats and without any tag in `exclude`. An unusable reply gives no tags."""
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", response.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(text[text.index("["): text.rindex("]") + 1])
    except ValueError:
        return []
    tags: list[str] = []
    for item in data if isinstance(data, list) else []:
        tag = clean_tag(item) if isinstance(item, str) else ""
        if tag and tag not in exclude and tag not in tags:
            tags.append(tag)
    return tags[:MAX_NEW]


class TagWriter:
    def __init__(self, gateway: AgentGateway, directory: AgentDirectory) -> None:
        self._gateway = gateway
        self._directory = directory

    async def generate(self, caller: Caller, title: str, body: str, known: list[str], on_note: list[str]) -> list[str]:
        """Up to three new tags for the note. `known`: the account's tags, most used first;
        `on_note`: the tags the note has already."""
        excerpt = f"{title.strip()}\n{body.strip()}".strip()[:EXCERPT_MAX]
        if not excerpt:
            return []
        agent = await self._directory.get(TAG_AGENT_ID)
        if agent is None:
            raise TagWriterUnavailable("the tag-writer agent is not running")
        try:
            result = await self._gateway.interpret(agent.url, caller, tag_prompt(excerpt, known))
        except AgentCallError as error:
            logger.info("tag generation skipped: %s", error)
            raise TagWriterUnavailable("the tag-writer agent did not answer") from error
        return parse_tags(str(result.get("response") or ""), {t.strip().lower() for t in [*known, *on_note]})
