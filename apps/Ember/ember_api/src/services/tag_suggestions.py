"""Tag suggestions for a note: which of the account's existing tags fit it.

Laya (ai_agent's local typed-question model) answers one yes/no question per candidate
tag, "is this note about <tag>?". It reads at most 512 tokens, so the note is cut to a
short excerpt, only a few tags are asked at once and only the most used ones are
checked. Only confident yes answers are suggested: Laya's confidence is uncalibrated
and a wrong suggestion costs the user more than a missing one. The user decides; this
never changes a note.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from src.services.agent_directory import AgentDirectory, AgentEntry
from src.services.agent_gateway import AgentCallError, AgentGateway, Caller

logger = logging.getLogger(__name__)

LAYA_PROVIDER = "laya"
MAX_CANDIDATES = 8  # existing tags checked per request (Laya takes 8 questions at most)
BATCH = 4  # questions per call: every question also uses part of Laya's 512 tokens
EXCERPT_MAX = 700  # characters of title and text the model reads
MAX_SUGGESTIONS = 5
MIN_YES = 0.5
TIME_LIMIT = 30.0  # seconds for the whole request, so a busy Laya cannot hold the page open
_TOO_LONG = "complete input"  # part of ai_agent's "Laya could not read the complete input" error


class TagSuggestionUnavailable(Exception):
    """Laya could not be asked or gave an answer that cannot be used."""


@dataclass(frozen=True)
class Suggestions:
    suggested: list[str]
    checked: int  # candidate tags Laya looked at
    skipped: int  # candidate tags left out: over the per-request cap, or too much text for Laya


async def _ignore_event(_event: dict[str, Any]) -> None:
    return None


def build_request(excerpt: str, tags: list[str]) -> str:
    """ai_agent's Laya question format: a text and one noul (yes/no) question per tag."""
    questions = {
        f"q{i}": {
            "type": "noul",
            "instructions": f'Is this note about "{tag}"?',
            "criteria": {"false": f"It is not about {tag}.", "true": f"It is about {tag}."},
        }
        for i, tag in enumerate(tags)
    }
    # local_only: Laya's own English model answers; a note never goes on to the fallback classifier (Jev).
    return json.dumps({"text": excerpt, "questions": questions, "local_only": True})


def confident_yes(response: str, tags: list[str]) -> dict[str, float]:
    """tag -> yes probability for the tags Laya answered yes to without doubt.
    Raises TagSuggestionUnavailable for an answer that is not the expected JSON."""
    try:
        answers = json.loads(response)["answers"]
        found: dict[str, float] = {}
        for i, tag in enumerate(tags):
            answer = answers[f"q{i}"]
            yes = answer["noul"]
            if answer["uncertain"] is False and not isinstance(yes, bool) and isinstance(yes, (int, float)) and yes >= MIN_YES:
                found[tag] = float(yes)
        return found
    except (ValueError, KeyError, TypeError) as error:
        raise TagSuggestionUnavailable("Laya gave an answer that could not be read") from error


class TagSuggester:
    def __init__(self, gateway: AgentGateway, directory: AgentDirectory) -> None:
        self._gateway = gateway
        self._directory = directory

    async def suggest(
        self, caller: Caller, title: str, body: str, candidates: list[str]
    ) -> Suggestions:
        """`candidates`: the account's tags not on the note yet, most used first."""
        chosen = candidates[:MAX_CANDIDATES]
        over_cap = len(candidates) - len(chosen)
        excerpt = f"{title.strip()}\n{body.strip()}".strip()[:EXCERPT_MAX]
        if not chosen or not excerpt:
            return Suggestions([], 0, over_cap)
        agent = await self._directory.find_by_provider(LAYA_PROVIDER)
        if agent is None:
            raise TagSuggestionUnavailable("the Laya agent is not running")
        try:
            async with asyncio.timeout(TIME_LIMIT):  # Laya handles one question set at a time
                scores, unreadable = await self._score(agent, caller, excerpt, chosen)
        except TimeoutError as error:
            raise TagSuggestionUnavailable("Laya took too long") from error
        best = sorted(scores, key=lambda tag: -scores[tag])[:MAX_SUGGESTIONS]
        return Suggestions(best, len(chosen) - unreadable, over_cap + unreadable)

    async def _score(
        self, agent: AgentEntry, caller: Caller, excerpt: str, chosen: list[str]
    ) -> tuple[dict[str, float], int]:
        scores: dict[str, float] = {}
        unreadable = 0
        for start in range(0, len(chosen), BATCH):
            found, left_out = await self._ask(agent, caller, excerpt, chosen[start : start + BATCH])
            scores.update(found)
            unreadable += left_out
        return scores, unreadable

    async def _ask(
        self, agent: AgentEntry, caller: Caller, excerpt: str, tags: list[str]
    ) -> tuple[dict[str, float], int]:
        """(confident yes answers, number of tags that could not be checked). A batch
        Laya finds too long is asked again one tag at a time."""
        try:
            result = await self._gateway.ask(
                agent.url, caller, question=build_request(excerpt, tags), history=[],
                request_id=uuid.uuid4().hex, caveman=False, enabled_extensions=[], on_event=_ignore_event,
            )
        except AgentCallError as error:
            if _TOO_LONG in str(error):
                if len(tags) > 1:
                    found: dict[str, float] = {}
                    left_out = 0
                    for tag in tags:
                        one, missed = await self._ask(agent, caller, excerpt, [tag])
                        found.update(one)
                        left_out += missed
                    return found, left_out
                return {}, 1
            logger.info("tag suggestion skipped: %s", error)
            raise TagSuggestionUnavailable("Laya did not answer") from error
        return confident_yes(str(result.get("response") or ""), tags), 0
