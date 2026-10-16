import chess
import pytest

from src.games.base import IllegalMove, InvalidOptions
from src.games.chess_game import MATE, ChessGame

game = ChessGame()
START = chess.STARTING_FEN
# White to move and mate in one with Qxf7#.
SCHOLARS = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"


def test_new_state_and_sides():
    assert game.new_state({}) == START
    assert game.assign_sides({}) == ("white", "black")
    assert game.assign_sides({"player_side": "black"}) == ("black", "white")


@pytest.mark.parametrize("options", [{"player_side": "green"}, {"speed": 1}])
def test_bad_options_are_rejected(options):
    with pytest.raises(InvalidOptions):
        game.new_state(options)


def test_legal_moves_at_the_start():
    assert len(game.legal_moves(START)) == 20
    assert game.side_to_move(START) == "white"


def test_apply_a_legal_move():
    after = game.apply(START, {"uci": "e2e4"})
    assert game.side_to_move(after) == "black"


@pytest.mark.parametrize("move", [{"uci": "e2e5"}, {"uci": "zz"}, {"uci": 5}, {}])
def test_illegal_moves_are_rejected(move):
    with pytest.raises(IllegalMove):
        game.apply(START, move)


def test_checkmate_status():
    state = game.apply(SCHOLARS, {"uci": "h5f7"})
    status = game.status(state)
    assert (status.finished, status.winner, status.reason) == (True, "white", "checkmate")
    assert game.side_to_move(state) is None


def test_ongoing_status():
    assert game.status(START).finished is False


def test_candidates_find_mate_in_one():
    best = game.candidates(SCHOLARS, k=3, depth=1, time_limit=5.0)[0]
    assert best.move == {"uci": "h5f7"}
    assert best.score > MATE / 2


def test_candidates_are_sorted_and_limited():
    cands = game.candidates(START, k=4, depth=2, time_limit=5.0)
    assert len(cands) == 4
    assert [c.score for c in cands] == sorted((c.score for c in cands), reverse=True)


def test_candidates_take_a_free_queen():
    # Black queen hangs on d5 to the white pawn on e4.
    fen = "rnb1kbnr/ppp1pppp/8/3q4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3"
    assert game.candidates(fen, k=1, depth=2, time_limit=5.0)[0].move == {"uci": "e4d5"}


def test_no_candidates_when_the_game_is_over():
    mated = game.apply(SCHOLARS, {"uci": "h5f7"})
    assert game.candidates(mated, k=3, depth=2, time_limit=1.0) == []


def test_timeout_keeps_the_last_finished_depth():
    # time_limit=0 makes every search past depth 1 time out mid-move; the board
    # must be left intact and the depth-1 ranking returned.
    cands = game.candidates(START, k=3, depth=6, time_limit=0.0)
    assert len(cands) == 3
    assert cands == game.candidates(START, k=3, depth=1, time_limit=5.0)


def test_evaluate_is_symmetric():
    state = game.apply(START, {"uci": "e2e4"})
    assert game.evaluate(state, "white") == -game.evaluate(state, "black")


def test_summary_and_description():
    cand = game.candidates(SCHOLARS, k=1, depth=1, time_limit=5.0)[0]
    assert game.summarize(SCHOLARS, cand) == "Qxf7# (capture, check, forced mate)"
    assert game.describe_position(START) == "White to move, move 1, material +0 for white."


def test_to_dict_lists_legal_moves():
    data = game.to_dict(START)
    assert data["turn"] == "white" and len(data["legal_moves"]) == 20
