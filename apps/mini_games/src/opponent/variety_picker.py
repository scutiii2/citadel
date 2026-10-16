"""A weighted random pick among the engine's top candidates: human-like play
without any model. Better-ranked candidates are more likely."""

from __future__ import annotations

import random
from typing import Any

from src.config import Difficulty
from src.games.base import Game
from src.opponent.base import Pick, top_candidates


class VarietyPicker:
    name = "variety"

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()

    async def pick(self, game: Game, state: Any, difficulty: Difficulty) -> Pick:
        cands = await top_candidates(game, state, difficulty)
        weights = [1.0 / (rank + 1) for rank in range(len(cands))]
        return Pick(self._rng.choices(cands, weights=weights)[0].move, "variety")
