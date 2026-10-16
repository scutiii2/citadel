"""The Picker interface: choose the bot's move for a position."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from src.config import Difficulty
from src.games.base import Candidate, Game, GameError, Move


@dataclass(frozen=True)
class Pick:
    move: Move
    source: str  # "engine", "variety", "laya" or "fallback" (Laya was asked but not used)


class Picker(Protocol):
    name: str

    async def pick(self, game: Game, state: Any, difficulty: Difficulty) -> Pick: ...


async def top_candidates(game: Game, state: Any, difficulty: Difficulty) -> list[Candidate]:
    """The engine's best moves, searched off the event loop."""
    cands = await asyncio.to_thread(game.candidates, state, difficulty.k, difficulty.depth, difficulty.time_limit)
    if not cands:
        raise GameError("the bot has no legal move")
    return cands
