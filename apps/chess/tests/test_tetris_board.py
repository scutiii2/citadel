import pytest

from src.games.tetris_board import (
    COLS,
    EMPTY_BOARD,
    PIECES,
    ROTATIONS,
    ROWS,
    bumpiness,
    column_heights,
    count_holes,
    landing_row,
    lock,
    piece_at,
    placement_score,
    placements,
)


def _board(rows: dict[int, str]):
    """Board from {row index: 10-char string of '#' and '.'}."""
    grid = [[0] * COLS for _ in range(ROWS)]
    for index, text in rows.items():
        grid[index] = [1 if ch == "#" else 0 for ch in text]
    return tuple(tuple(r) for r in grid)


@pytest.mark.parametrize("piece,count", [("I", 2), ("O", 1), ("T", 4), ("S", 2), ("Z", 2), ("J", 4), ("L", 4)])
def test_distinct_rotation_counts(piece, count):
    assert len(ROTATIONS[piece]) == count


def test_every_rotation_has_four_cells_at_the_origin():
    for rotations in ROTATIONS.values():
        for cells in rotations:
            assert len(cells) == 4
            assert min(r for r, _ in cells) == 0 and min(c for _, c in cells) == 0


def test_piece_sequence_is_seeded_and_a_seven_bag():
    first = [piece_at(7, i) for i in range(14)]
    assert first == [piece_at(7, i) for i in range(14)]
    assert sorted(first[:7]) == sorted(PIECES) and sorted(first[7:]) == sorted(PIECES)
    assert first != [piece_at(8, i) for i in range(14)]


def test_placement_counts():
    assert len(placements("O")) == 9
    assert len(placements("I")) == 7 + 10  # flat I fits 7 columns, upright I fits 10


def test_o_drops_to_the_floor():
    cells = ROTATIONS["O"][0]
    assert landing_row(EMPTY_BOARD, cells, 0) == ROWS - 2


def test_piece_rests_on_the_stack():
    board = _board({ROWS - 1: "#" * COLS})
    assert landing_row(board, ROTATIONS["O"][0], 3) == ROWS - 3


def test_full_stack_cannot_spawn():
    board = _board({0: "#" * COLS})
    assert landing_row(board, ROTATIONS["O"][0], 0) is None


def test_lock_clears_full_lines():
    board = _board({ROWS - 1: "########.."})
    after, cleared = lock(board, ROTATIONS["O"][0], ROWS - 2, 8)
    assert cleared == 1
    assert sum(map(sum, after)) == 2  # the O's upper half is left
    assert all(not any(r) for r in after[: ROWS - 2])


def test_heights_holes_and_bumpiness():
    board = _board({ROWS - 3: "#.........", ROWS - 2: "..........", ROWS - 1: "#........."})
    assert column_heights(board)[:2] == [3, 0]
    assert count_holes(board) == 1
    assert bumpiness([3, 0, 0]) == 3


def test_flat_placement_scores_higher_than_a_tall_one():
    flat, _ = lock(EMPTY_BOARD, ROTATIONS["I"][0], ROWS - 1, 0)
    tall, _ = lock(EMPTY_BOARD, ROTATIONS["I"][1], ROWS - 4, 0)
    assert placement_score(flat, 0) > placement_score(tall, 0)
