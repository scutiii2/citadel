"""Tetris pieces, the 10 by 20 board and placement scoring. Pure functions."""

from __future__ import annotations

import random

ROWS, COLS = 20, 10
Cells = tuple[tuple[int, int], ...]
Board = tuple[tuple[int, ...], ...]

_SHAPES: dict[str, Cells] = {
    "I": ((0, 0), (0, 1), (0, 2), (0, 3)),
    "O": ((0, 0), (0, 1), (1, 0), (1, 1)),
    "T": ((0, 1), (1, 0), (1, 1), (1, 2)),
    "S": ((0, 1), (0, 2), (1, 0), (1, 1)),
    "Z": ((0, 0), (0, 1), (1, 1), (1, 2)),
    "J": ((0, 0), (1, 0), (1, 1), (1, 2)),
    "L": ((0, 2), (1, 0), (1, 1), (1, 2)),
}
PIECES = tuple(_SHAPES)
EMPTY_BOARD: Board = tuple(tuple(0 for _ in range(COLS)) for _ in range(ROWS))


def _normalise(cells) -> Cells:
    min_r = min(r for r, _ in cells)
    min_c = min(c for _, c in cells)
    return tuple(sorted((r - min_r, c - min_c) for r, c in cells))


def _rotations(piece: str) -> tuple[Cells, ...]:
    """The distinct rotations of a piece, each normalised to the top-left."""
    seen: list[Cells] = []
    cells = _normalise(_SHAPES[piece])
    while cells not in seen:
        seen.append(cells)
        cells = _normalise([(c, -r) for r, c in cells])
    return tuple(seen)


ROTATIONS: dict[str, tuple[Cells, ...]] = {piece: _rotations(piece) for piece in PIECES}


def piece_at(seed: int, index: int) -> str:
    """The index-th piece of the seeded 7-bag sequence; stateless."""
    bag = list(PIECES)
    random.Random(f"{seed}:{index // 7}").shuffle(bag)
    return bag[index % 7]


def placements(piece: str) -> list[tuple[int, int]]:
    """Every (rotation, leftmost column) that fits inside the board width."""
    result = []
    for rotation, cells in enumerate(ROTATIONS[piece]):
        width = max(c for _, c in cells) + 1
        result.extend((rotation, column) for column in range(COLS - width + 1))
    return result


def _collides(board: Board, cells: Cells, row: int, column: int) -> bool:
    return any(r + row >= ROWS or board[r + row][c + column] for r, c in cells)


def landing_row(board: Board, cells: Cells, column: int) -> int | None:
    """Row the piece's top edge rests at after a straight drop, or None when
    it cannot even spawn (the stack reached the top)."""
    if _collides(board, cells, 0, column):
        return None
    row = 0
    while not _collides(board, cells, row + 1, column):
        row += 1
    return row


def lock(board: Board, cells: Cells, row: int, column: int) -> tuple[Board, int]:
    """Place the piece, clear full lines; returns the new board and the count."""
    grid = [list(r) for r in board]
    for r, c in cells:
        grid[r + row][c + column] = 1
    kept = [r for r in grid if not all(r)]
    cleared = ROWS - len(kept)
    rows = [[0] * COLS for _ in range(cleared)] + kept
    return tuple(tuple(r) for r in rows), cleared


def column_heights(board: Board) -> list[int]:
    heights = []
    for c in range(COLS):
        top = next((r for r in range(ROWS) if board[r][c]), ROWS)
        heights.append(ROWS - top)
    return heights


def count_holes(board: Board) -> int:
    holes = 0
    for c in range(COLS):
        seen = False
        for r in range(ROWS):
            if board[r][c]:
                seen = True
            elif seen:
                holes += 1
    return holes


def bumpiness(heights: list[int]) -> int:
    return sum(abs(a - b) for a, b in zip(heights, heights[1:]))


def placement_score(board: Board, lines: int) -> float:
    """Standard stacking heuristic: reward cleared lines, punish height,
    holes and an uneven surface. Higher is better."""
    heights = column_heights(board)
    return -0.51 * sum(heights) + 0.76 * lines - 0.36 * count_holes(board) - 0.18 * bumpiness(heights)
