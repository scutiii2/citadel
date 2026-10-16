import asyncio
import random

import pytest

from src.config import Difficulty
from src.games.base import GameError
from src.games.chess_game import ChessGame
from src.games.tetris_game import TetrisGame
from src.opponent.engine_picker import EnginePicker
from src.opponent.laya_client import LayaClient
from src.opponent.laya_picker import LayaPicker
from src.opponent.variety_picker import VarietyPicker
from tests.fake_laya import FakeEngine

chess_game = ChessGame()
START = chess_game.new_state({})
EASY = Difficulty(depth=1, k=4, time_limit=2.0, trust_uncertain=False)
TRUSTING = Difficulty(depth=1, k=4, time_limit=2.0, trust_uncertain=True)


def pick(picker, game=chess_game, state=START, difficulty=EASY):
    return asyncio.run(picker.pick(game, state, difficulty))


def best_move(difficulty=EASY):
    return chess_game.candidates(START, difficulty.k, difficulty.depth, difficulty.time_limit)[0].move


def test_engine_picker_takes_the_best_candidate():
    result = pick(EnginePicker())
    assert (result.move, result.source) == (best_move(), "engine")


def test_variety_picker_stays_within_the_top_candidates():
    allowed = [c.move for c in chess_game.candidates(START, 4, 1, 2.0)]
    picker = VarietyPicker(random.Random(1))
    results = {tuple(pick(picker).move.items()) for _ in range(30)}
    assert results <= {tuple(m.items()) for m in allowed} and len(results) > 1


def test_variety_picker_is_reproducible_with_a_seed():
    a = [pick(VarietyPicker(random.Random(5))).move for _ in range(3)]
    b = [pick(VarietyPicker(random.Random(5))).move for _ in range(3)]
    assert a == b


def test_laya_picker_uses_the_option_laya_chooses():
    cands = chess_game.candidates(START, 4, 1, 2.0)
    picker = LayaPicker(LayaClient(FakeEngine(pick="c", confidence=0.9)))
    result = pick(picker)
    assert (result.move, result.source) == (cands[2].move, "laya")


def test_laya_question_lists_each_candidate_summary():
    engine = FakeEngine()
    pick(LayaPicker(LayaClient(engine)))
    text, questions = engine.calls[0]
    criteria = questions["move"]["criteria"]
    assert list(criteria) == ["a", "b", "c", "d"] and text.startswith("White to move")
    assert all("eval" in line for line in criteria.values())


def test_uncertain_laya_falls_back_to_the_engine():
    picker = LayaPicker(LayaClient(FakeEngine(pick="d", confidence=0.5)))
    result = pick(picker)
    assert (result.move, result.source) == (best_move(), "fallback")


def test_trusting_difficulty_accepts_an_uncertain_answer():
    cands = chess_game.candidates(START, 4, 1, 2.0)
    picker = LayaPicker(LayaClient(FakeEngine(pick="d", confidence=0.5)))
    result = pick(picker, difficulty=TRUSTING)
    assert (result.move, result.source) == (cands[3].move, "laya")


def test_laya_exception_falls_back_to_the_engine():
    result = pick(LayaPicker(LayaClient(FakeEngine(usage={"truncated": True}))))
    assert (result.move, result.source) == (best_move(), "fallback")


def test_laya_timeout_falls_back_to_the_engine():
    result = pick(LayaPicker(LayaClient(FakeEngine(delay=0.5), timeout=0.05)))
    assert result.source == "fallback"


def test_missing_laya_package_falls_back():
    client = LayaClient()
    if client.is_available():
        pytest.skip("laya is installed here")
    assert pick(LayaPicker(client)).source == "fallback"


def test_single_candidate_skips_laya():
    engine = FakeEngine()
    one = Difficulty(depth=1, k=1, time_limit=1.0, trust_uncertain=False)
    result = pick(LayaPicker(LayaClient(engine)), difficulty=one)
    assert result.source == "engine" and engine.calls == []


def test_pickers_work_for_tetris_too():
    tetris = TetrisGame()
    state = tetris.new_state({"seed": 4})
    result = pick(LayaPicker(LayaClient(FakeEngine(pick="b", confidence=0.95))), game=tetris, state=state)
    assert result.source == "laya" and set(result.move) == {"rotation", "column"}


def test_no_legal_move_is_a_game_error():
    tetris = TetrisGame()
    state = tetris.new_state({"seed": 4, "piece_limit": 5})
    state = type(state)(**{**state.__dict__, "placed": (5, 5)})
    with pytest.raises(GameError):
        pick(EnginePicker(), game=tetris, state=state)
