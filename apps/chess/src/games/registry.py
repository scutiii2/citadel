"""The games the backend can host. A new game is one plugin file plus a line here."""

from __future__ import annotations

from src.games.base import Game, InvalidOptions
from src.games.chess_game import ChessGame
from src.games.tetris_game import TetrisGame


def build_games() -> dict[str, Game]:
    return {game.id: game for game in (ChessGame(), TetrisGame())}


def get_game(games: dict[str, Game], game_id: object) -> Game:
    if not isinstance(game_id, str) or game_id not in games:
        raise InvalidOptions(f"unknown game {game_id!r}; valid games: {', '.join(sorted(games))}")
    return games[game_id]
