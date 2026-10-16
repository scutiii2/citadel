"""Laya chooses among the engine's top candidates.

The engine proposes and scores the moves; Laya reads a short text summary of
the position and one feature line per candidate and picks one. The engine's
best move is the fallback whenever Laya is uncertain (unless the difficulty
trusts uncertain answers), unavailable, slow or wrong. A Laya failure never
fails a turn.
"""

from __future__ import annotations

import logging
from typing import Any

from src.config import Difficulty
from src.games.base import Game
from src.opponent.base import Pick, top_candidates
from src.opponent.laya_client import MAX_TEXT_CHARS, LayaClient, LayaError

log = logging.getLogger(__name__)
INSTRUCTIONS = "Which candidate move is the strongest for the side to move?"


class LayaPicker:
    name = "laya"

    def __init__(self, client: LayaClient, min_confidence: float = 0.7) -> None:
        self._client = client
        self._min_confidence = min_confidence

    async def pick(self, game: Game, state: Any, difficulty: Difficulty) -> Pick:
        cands = await top_candidates(game, state, difficulty)
        if len(cands) < 2:
            return Pick(cands[0].move, "engine")
        keys = [chr(ord("a") + i) for i in range(len(cands))]
        options = {key: game.summarize(state, cand) for key, cand in zip(keys, cands)}
        try:
            choice = await self._client.choose(
                game.describe_position(state)[:MAX_TEXT_CHARS], INSTRUCTIONS, options, self._min_confidence
            )
        except LayaError as error:
            log.warning("Laya unavailable for this move, using the engine: %s", error)
            return Pick(cands[0].move, "fallback")
        if choice.uncertain and not difficulty.trust_uncertain:
            return Pick(cands[0].move, "fallback")
        return Pick(cands[keys.index(choice.key)].move, "laya")
