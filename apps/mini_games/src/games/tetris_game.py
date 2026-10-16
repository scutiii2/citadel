"""Tetris versus plugin: player and bot stack the same seeded pieces on their
own boards, in lockstep (player places piece n, then the bot places piece n).

A move is a placement {"rotation": int, "column": int}; column is the
leftmost column of the rotated piece. The browser owns gravity and sends the
final placement; this plugin only validates and simulates the drop.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Any

from src.games.base import Candidate, IllegalMove, InvalidOptions, Move, Status
from src.games.tetris_board import (
    COLS,
    EMPTY_BOARD,
    ROTATIONS,
    Board,
    bumpiness,
    column_heights,
    count_holes,
    landing_row,
    lock,
    piece_at,
    placement_score,
    placements,
)

SIDES = ("player", "bot")
LINE_POINTS = (0, 100, 300, 500, 800)
DEFAULT_PIECE_LIMIT = 40
MIN_PIECE_LIMIT, MAX_PIECE_LIMIT = 5, 200
_TOP_OUT_SCORE = -1e9


@dataclass(frozen=True)
class TetrisState:
    seed: int
    piece_limit: int
    boards: tuple[Board, Board]
    scores: tuple[int, int]
    placed: tuple[int, int]
    topped_out: tuple[bool, bool]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class TetrisGame:
    id = "tetris"

    def option_schema(self) -> dict[str, Any]:
        return {
            "seed": {"type": "integer", "default": "random"},
            "piece_limit": {
                "type": "integer", "minimum": MIN_PIECE_LIMIT, "maximum": MAX_PIECE_LIMIT,
                "default": DEFAULT_PIECE_LIMIT,
            },
        }

    def assign_sides(self, options: dict[str, Any]) -> tuple[str, str]:
        return SIDES

    def new_state(self, options: dict[str, Any]) -> TetrisState:
        unknown = set(options) - {"seed", "piece_limit"}
        if unknown:
            raise InvalidOptions(f"unknown tetris option(s): {', '.join(sorted(unknown))}")
        seed = options.get("seed", random.randrange(2**31))
        limit = options.get("piece_limit", DEFAULT_PIECE_LIMIT)
        if not _is_int(seed):
            raise InvalidOptions("seed must be an integer")
        if not _is_int(limit) or not MIN_PIECE_LIMIT <= limit <= MAX_PIECE_LIMIT:
            raise InvalidOptions(f"piece_limit must be an integer from {MIN_PIECE_LIMIT} to {MAX_PIECE_LIMIT}")
        return TetrisState(seed, limit, (EMPTY_BOARD, EMPTY_BOARD), (0, 0), (0, 0), (False, False))

    # -- turn and piece bookkeeping ------------------------------------------------

    def _finished(self, state: TetrisState) -> bool:
        return any(state.topped_out) or all(n >= state.piece_limit for n in state.placed)

    def side_to_move(self, state: TetrisState) -> str | None:
        if self._finished(state):
            return None
        return SIDES[0 if state.placed[0] == state.placed[1] else 1]

    def _piece(self, state: TetrisState, index: int) -> str:
        return piece_at(state.seed, state.placed[index])

    # -- rules ---------------------------------------------------------------------

    def legal_moves(self, state: TetrisState) -> list[Move]:
        side = self.side_to_move(state)
        if side is None:
            return []
        piece = self._piece(state, SIDES.index(side))
        return [{"rotation": r, "column": c} for r, c in placements(piece)]

    def apply(self, state: TetrisState, move: Move) -> TetrisState:
        side = self.side_to_move(state)
        if side is None:
            raise IllegalMove("the game is over")
        index = SIDES.index(side)
        piece = self._piece(state, index)
        rotation = move.get("rotation") if isinstance(move, dict) else None
        column = move.get("column") if isinstance(move, dict) else None
        if (rotation, column) not in placements(piece) or not (_is_int(rotation) and _is_int(column)):
            raise IllegalMove(f"{piece} cannot be placed at rotation {rotation!r}, column {column!r}")
        cells = ROTATIONS[piece][rotation]
        row = landing_row(state.boards[index], cells, column)
        placed = _set(state.placed, index, state.placed[index] + 1)
        if row is None:
            return replace(state, placed=placed, topped_out=_set(state.topped_out, index, True))
        board, cleared = lock(state.boards[index], cells, row, column)
        return replace(
            state,
            boards=_set(state.boards, index, board),
            scores=_set(state.scores, index, state.scores[index] + LINE_POINTS[cleared]),
            placed=placed,
        )

    def status(self, state: TetrisState) -> Status:
        if not self._finished(state):
            return Status(False)
        if state.topped_out[0] != state.topped_out[1]:
            loser = SIDES[0 if state.topped_out[0] else 1]
            return Status(True, SIDES[1 - SIDES.index(loser)], f"{loser} topped out")
        if state.scores[0] == state.scores[1]:
            return Status(True, None, "equal scores at the piece limit")
        return Status(True, SIDES[0 if state.scores[0] > state.scores[1] else 1], "higher score at the piece limit")

    def evaluate(self, state: TetrisState, side: str) -> float:
        me = SIDES.index(side)
        return float(state.scores[me] - state.scores[1 - me])

    # -- engine --------------------------------------------------------------------

    def candidates(self, state: TetrisState, k: int, depth: int, time_limit: float) -> list[Candidate]:
        side = self.side_to_move(state)
        if side is None:
            return []
        index = SIDES.index(side)
        piece = self._piece(state, index)
        board = state.boards[index]
        scored = []
        for rotation, column in placements(piece):
            cells = ROTATIONS[piece][rotation]
            row = landing_row(board, cells, column)
            if row is None:
                continue
            after, cleared = lock(board, cells, row, column)
            heights = column_heights(after)
            features = {
                "rotation": rotation, "column": column, "lines": cleared,
                "holes": count_holes(after), "max_height": max(heights), "bumpiness": bumpiness(heights),
            }
            scored.append(Candidate({"rotation": rotation, "column": column}, placement_score(after, cleared), features))
        if not scored:  # every placement tops out; the game is lost whatever is sent
            rotation, column = placements(piece)[0]
            return [Candidate({"rotation": rotation, "column": column}, _TOP_OUT_SCORE, {"top_out": True})]
        scored.sort(key=lambda c: (-c.score, c.move["rotation"], c.move["column"]))
        return scored[:k]

    def summarize(self, state: TetrisState, candidate: Candidate) -> str:
        f = candidate.features
        if f.get("top_out"):
            return "any placement tops out"
        lines = f"clears {f['lines']} line{'s' if f['lines'] != 1 else ''}"
        holes = f"{f['holes']} hole{'s' if f['holes'] != 1 else ''}"
        return f"rotation {f['rotation']} at column {f['column']}: {lines}, {holes}, max height {f['max_height']}"

    def describe_position(self, state: TetrisState) -> str:
        side = self.side_to_move(state)
        if side is None:
            return "Game over."
        index = SIDES.index(side)
        board = state.boards[index]
        heights = " ".join(str(h) for h in column_heights(board))
        return (
            f"Piece {self._piece(state, index)}. Column heights {heights}. "
            f"Holes {count_holes(board)}. Score {state.scores[index]} to {state.scores[1 - index]}."
        )

    def to_dict(self, state: TetrisState) -> dict[str, Any]:
        side = self.side_to_move(state)
        upcoming = []
        if side is not None:
            start = state.placed[SIDES.index(side)]
            upcoming = [piece_at(state.seed, start + i) for i in range(4) if start + i < state.piece_limit]
        return {
            "seed": state.seed,
            "piece_limit": state.piece_limit,
            "columns": COLS,
            "boards": {s: [list(r) for r in state.boards[i]] for i, s in enumerate(SIDES)},
            "scores": dict(zip(SIDES, state.scores)),
            "placed": dict(zip(SIDES, state.placed)),
            "topped_out": dict(zip(SIDES, state.topped_out)),
            "turn": side,
            "current_piece": upcoming[0] if upcoming else None,
            "next_pieces": upcoming[1:],
        }


def _set(pair: tuple, index: int, value: Any) -> tuple:
    return tuple(value if i == index else v for i, v in enumerate(pair))
