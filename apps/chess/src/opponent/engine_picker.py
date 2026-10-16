"""Always the engine's best move."""

from __future__ import annotations

from typing import Any

from src.config import Difficulty
from src.games.base import Game
from src.opponent.base import Pick, top_candidates


class EnginePicker:
    name = "engine"

    async def pick(self, game: Game, state: Any, difficulty: Difficulty) -> Pick:
        return Pick((await top_candidates(game, state, difficulty))[0].move, "engine")
