"""Choose a turn's model tier from how hard the question looks.

When config_tuning.json's `classifier.auto_tier.enabled` is on and a backend of
the auto_tier chain is available (llm/decision.py), the user's question is classified as tiny, everyday,
large or hardest and mapped to a model tier. agent_config.run_chat resolves that
tier like a delegated one, so the agent's own min_tier/max_tier still cap it: an
agent capped at light stays on light. No answer (off, no key, a failure, low
confidence, a very short follow-up) means the default model, never an error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import anyio.to_thread

from src.providers.decision import decision

_log = logging.getLogger(__name__)

# A reply like "yes" or "do that" says nothing about the work it refers to.
_MIN_FOLLOW_UP_CHARS = 20


@dataclass(frozen=True)
class AutoTier:
    tier: str
    note: str


def enabled() -> bool:
    return decision.settings().auto_tier.enabled and decision.available("auto_tier")


async def pick(question: str, has_history: bool) -> AutoTier | None:
    """The tier for `question`, or None to keep the default model."""
    if not enabled():
        return None
    text = question.strip()
    if not text or (has_history and len(text) < _MIN_FOLLOW_UP_CHARS):
        return None
    config = decision.settings()
    try:
        picked = await anyio.to_thread.run_sync(decision.classify_size, text[: config.max_input_chars])
    except decision.ClassifierError as error:
        _log.warning("auto tier skipped: %s", error)
        return None
    if picked.confidence < config.auto_tier.min_confidence:
        return None
    tier = dict(config.auto_tier.tiers).get(picked.choice)
    if tier is None:
        return None
    return AutoTier(tier, f"auto tier: {picked.choice} ({picked.confidence}%) -> {tier}")
