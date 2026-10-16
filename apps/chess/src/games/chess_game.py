"""Chess plugin: python-chess rules plus a small alpha-beta engine.

State is a FEN string. A move is {"uci": "e2e4"}. Scores are in pawns from the
side to move's view; forced mates score +-MATE.
"""

from __future__ import annotations

import time
from typing import Any

import chess

from src.games.base import Candidate, IllegalMove, InvalidOptions, Move, Status

MATE = 10_000.0
_VALUES = {chess.PAWN: 1.0, chess.KNIGHT: 3.0, chess.BISHOP: 3.2, chess.ROOK: 5.0, chess.QUEEN: 9.0}
_CENTRE = (chess.D4, chess.E4, chess.D5, chess.E5)
_SIDES = ("white", "black")


class _Timeout(Exception):
    """The search ran out of time; the previous depth's result stands."""


def _static(board: chess.Board) -> float:
    """Material plus a small centre bonus, from the side to move's view."""
    me, them = board.turn, not board.turn
    score = 0.0
    for piece_type, value in _VALUES.items():
        score += value * (len(board.pieces(piece_type, me)) - len(board.pieces(piece_type, them)))
    for square in _CENTRE:
        piece = board.piece_at(square)
        if piece is not None and piece.piece_type in (chess.PAWN, chess.KNIGHT):
            score += 0.1 if piece.color == me else -0.1
    return score


def _ordered(board: chess.Board) -> list[chess.Move]:
    return sorted(board.legal_moves, key=lambda m: not board.is_capture(m))


def _negamax(board: chess.Board, depth: int, alpha: float, beta: float, ply: int, deadline: float | None) -> float:
    if board.is_checkmate():
        return -MATE + ply
    if board.is_stalemate() or board.is_insufficient_material():
        return 0.0
    if depth == 0:
        return _static(board)
    if deadline is not None and time.monotonic() > deadline:
        raise _Timeout
    best = -MATE * 2
    for move in _ordered(board):
        board.push(move)
        try:
            score = -_negamax(board, depth - 1, -beta, -alpha, ply + 1, deadline)
        finally:
            board.pop()  # also on _Timeout, so the caller's board is never left mid-search
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def _score_root(board: chess.Board, depth: int, deadline: float | None) -> list[tuple[chess.Move, float]]:
    scored = []
    for move in _ordered(board):
        board.push(move)
        try:
            score = -_negamax(board, depth - 1, -MATE * 2, MATE * 2, 1, deadline)
        finally:
            board.pop()
        scored.append((move, score))
    return scored


class ChessGame:
    id = "chess"

    def option_schema(self) -> dict[str, Any]:
        return {"player_side": {"type": "string", "enum": list(_SIDES), "default": "white"}}

    def _player_side(self, options: dict[str, Any]) -> str:
        unknown = set(options) - {"player_side"}
        if unknown:
            raise InvalidOptions(f"unknown chess option(s): {', '.join(sorted(unknown))}")
        side = options.get("player_side", "white")
        if side not in _SIDES:
            raise InvalidOptions("player_side must be 'white' or 'black'")
        return side

    def assign_sides(self, options: dict[str, Any]) -> tuple[str, str]:
        player = self._player_side(options)
        return player, "black" if player == "white" else "white"

    def new_state(self, options: dict[str, Any]) -> str:
        self._player_side(options)
        return chess.STARTING_FEN

    def side_to_move(self, state: str) -> str | None:
        board = chess.Board(state)
        if board.is_game_over(claim_draw=True):
            return None
        return "white" if board.turn else "black"

    def legal_moves(self, state: str) -> list[Move]:
        return [{"uci": m.uci()} for m in chess.Board(state).legal_moves]

    def apply(self, state: str, move: Move) -> str:
        board = chess.Board(state)
        uci = move.get("uci") if isinstance(move, dict) else None
        try:
            parsed = chess.Move.from_uci(uci) if isinstance(uci, str) else None
        except ValueError:
            parsed = None
        if parsed is None or parsed not in board.legal_moves:
            raise IllegalMove(f"illegal chess move: {uci!r}")
        board.push(parsed)
        return board.fen()

    def status(self, state: str) -> Status:
        outcome = chess.Board(state).outcome(claim_draw=True)
        if outcome is None:
            return Status(False)
        winner = None if outcome.winner is None else ("white" if outcome.winner else "black")
        return Status(True, winner, outcome.termination.name.lower())

    def evaluate(self, state: str, side: str) -> float:
        board = chess.Board(state)
        score = _static(board)
        return score if board.turn == (side == "white") else -score

    def candidates(self, state: str, k: int, depth: int, time_limit: float) -> list[Candidate]:
        board = chess.Board(state)
        if not any(board.legal_moves):
            return []
        deadline = time.monotonic() + time_limit
        scored: list[tuple[chess.Move, float]] = []
        for current in range(1, max(1, depth) + 1):
            try:
                scored = _score_root(board, current, None if current == 1 else deadline)
            except _Timeout:
                break
        scored.sort(key=lambda pair: -pair[1])
        return [self._candidate(board, move, score) for move, score in scored[:k]]

    @staticmethod
    def _candidate(board: chess.Board, move: chess.Move, score: float) -> Candidate:
        san = board.san(move)
        features = {
            "san": san,
            "capture": board.is_capture(move),
            "check": board.gives_check(move),
            "castle": board.is_castling(move),
            "promotion": move.promotion is not None,
        }
        return Candidate({"uci": move.uci()}, score, features)

    def summarize(self, state: str, candidate: Candidate) -> str:
        f = candidate.features
        tags = [name for name in ("capture", "check", "castle", "promotion") if f.get(name)] or ["quiet"]
        rating = "forced mate" if abs(candidate.score) > MATE / 2 else f"eval {candidate.score:+.1f}"
        return f"{f['san']} ({', '.join(tags)}, {rating})"

    def describe_position(self, state: str) -> str:
        board = chess.Board(state)
        material = sum(
            value * (len(board.pieces(t, chess.WHITE)) - len(board.pieces(t, chess.BLACK)))
            for t, value in _VALUES.items()
        )
        side = "White" if board.turn else "Black"
        check = ", in check" if board.is_check() else ""
        return f"{side} to move, move {board.fullmove_number}, material {material:+.0f} for white{check}."

    def to_dict(self, state: str) -> dict[str, Any]:
        board = chess.Board(state)
        return {
            "fen": state,
            "turn": "white" if board.turn else "black",
            "in_check": board.is_check(),
            "legal_moves": [m.uci() for m in board.legal_moves],
        }
