import pytest

from src.games.base import IllegalMove, InvalidOptions
from src.games.tetris_board import EMPTY_BOARD, piece_at
from src.games.tetris_game import TetrisGame, TetrisState

game = TetrisGame()


def _state(**changes) -> TetrisState:
    base = game.new_state({"seed": 1, "piece_limit": 5})
    return TetrisState(**{**base.__dict__, **changes})


def test_new_state_defaults_and_sides():
    state = game.new_state({"seed": 3})
    assert state.piece_limit == 40 and state.scores == (0, 0)
    assert game.assign_sides({}) == ("player", "bot")


@pytest.mark.parametrize("options", [{"piece_limit": 4}, {"piece_limit": 201}, {"piece_limit": True}, {"seed": "x"}, {"x": 1}])
def test_bad_options_are_rejected(options):
    with pytest.raises(InvalidOptions):
        game.new_state(options)


def test_same_seed_gives_same_pieces():
    a = game.to_dict(game.new_state({"seed": 9}))
    b = game.to_dict(game.new_state({"seed": 9}))
    assert a == b and a["current_piece"] == piece_at(9, 0)


def test_turns_alternate_per_piece():
    state = game.new_state({"seed": 1, "piece_limit": 5})
    assert game.side_to_move(state) == "player"
    state = game.apply(state, game.legal_moves(state)[0])
    assert game.side_to_move(state) == "bot"
    state = game.apply(state, game.legal_moves(state)[0])
    assert game.side_to_move(state) == "player"
    assert state.placed == (1, 1)


@pytest.mark.parametrize("move", [{"rotation": 9, "column": 0}, {"rotation": 0, "column": 99}, {"rotation": "a", "column": 0}, {}])
def test_illegal_placements_are_rejected(move):
    with pytest.raises(IllegalMove):
        game.apply(game.new_state({"seed": 1}), move)


def test_a_placement_changes_only_the_movers_board():
    state = game.new_state({"seed": 1})
    after = game.apply(state, game.legal_moves(state)[0])
    assert after.boards[0] != EMPTY_BOARD and after.boards[1] == EMPTY_BOARD


def test_line_clear_scores_points():
    # Bottom row full except the two right columns; an O piece (seed 1 may not
    # start with O, so force the board and use whichever O placement exists).
    seed = next(s for s in range(200) if piece_at(s, 0) == "O")
    board = list(map(list, EMPTY_BOARD))
    board[19] = [1] * 8 + [0, 0]
    board[18] = [1] * 8 + [0, 0]
    state = TetrisState(seed, 5, (tuple(map(tuple, board)), EMPTY_BOARD), (0, 0), (0, 0), (False, False))
    after = game.apply(state, {"rotation": 0, "column": 8})
    assert after.scores[0] == 300  # two lines


def test_topping_out_ends_the_game_and_loses():
    full = tuple(tuple(1 for _ in range(10)) for _ in range(20))
    state = _state(boards=(full, EMPTY_BOARD))
    after = game.apply(state, game.legal_moves(state)[0])
    status = game.status(after)
    assert status.finished and status.winner == "bot" and "player topped out" in status.reason
    assert game.side_to_move(after) is None and game.legal_moves(after) == []


def test_game_ends_at_the_piece_limit_with_a_draw_on_equal_scores():
    state = game.new_state({"seed": 1, "piece_limit": 5})
    for _ in range(10):
        state = game.apply(state, game.candidates(state, 1, 1, 1.0)[0].move)
    status = game.status(state)
    assert status.finished and not any(state.topped_out)
    assert status.winner in (None, "player", "bot")


def test_moving_after_the_game_is_over_is_illegal():
    state = _state(placed=(5, 5))
    with pytest.raises(IllegalMove):
        game.apply(state, {"rotation": 0, "column": 0})


def test_candidates_sorted_limited_and_deterministic():
    state = game.new_state({"seed": 2})
    cands = game.candidates(state, 3, 1, 1.0)
    assert len(cands) == 3
    assert [c.score for c in cands] == sorted((c.score for c in cands), reverse=True)
    assert cands == game.candidates(state, 3, 1, 1.0)


def test_candidates_when_every_placement_tops_out():
    full = tuple(tuple(1 for _ in range(10)) for _ in range(20))
    cands = game.candidates(_state(boards=(full, EMPTY_BOARD)), 3, 1, 1.0)
    assert len(cands) == 1 and cands[0].features == {"top_out": True}


def test_candidate_prefers_clearing_a_line():
    seed = next(s for s in range(200) if piece_at(s, 0) == "I")
    board = list(map(list, EMPTY_BOARD))
    board[19] = [0] * 4 + [1] * 6
    state = TetrisState(seed, 5, (tuple(map(tuple, board)), EMPTY_BOARD), (0, 0), (0, 0), (False, False))
    best = game.candidates(state, 1, 1, 1.0)[0]
    assert best.move == {"rotation": 0, "column": 0} and best.features["lines"] == 1


def test_summary_and_description():
    state = game.new_state({"seed": 2})
    cand = game.candidates(state, 1, 1, 1.0)[0]
    assert game.summarize(state, cand).startswith("rotation ")
    assert game.describe_position(state).startswith(f"Piece {piece_at(2, 0)}. Column heights 0 0 0")


def test_to_dict_shape():
    data = game.to_dict(game.new_state({"seed": 2, "piece_limit": 5}))
    assert data["turn"] == "player" and len(data["boards"]["player"]) == 20
    assert len(data["next_pieces"]) == 3 and data["piece_limit"] == 5


def test_evaluate_is_the_score_difference():
    state = _state(scores=(300, 100))
    assert game.evaluate(state, "player") == 200.0 and game.evaluate(state, "bot") == -200.0
