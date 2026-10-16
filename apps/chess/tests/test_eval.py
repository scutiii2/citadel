import asyncio
import random
from datetime import date

from src.eval.laya_eval import MIN_SAMPLES, evaluate_game, render_report, sample_states
from src.games.chess_game import ChessGame
from src.games.tetris_game import TetrisGame
from src.opponent.laya_client import LayaClient
from tests.fake_laya import FakeEngine


def run_eval(game, engine, positions=MIN_SAMPLES):
    return asyncio.run(evaluate_game(game, LayaClient(engine), positions, k=4, depth=1, seed=1))


def test_sampled_positions_are_unfinished_and_reproducible():
    game = ChessGame()
    a = sample_states(game, 5, random.Random(3))
    assert a == sample_states(game, 5, random.Random(3))
    assert len(a) == 5 and all(not game.status(s).finished for s in a)


def test_tetris_positions_can_be_sampled_too():
    game = TetrisGame()
    states = sample_states(game, 5, random.Random(3))
    assert len(states) == 5


def test_always_best_laya_beats_random():
    # "a" is always the engine's best candidate, so Laya loses nothing.
    report = run_eval(ChessGame(), FakeEngine(pick="a"))
    assert report.samples == MIN_SAMPLES and report.failures == 0
    assert report.laya_agreement == 1.0 and report.laya_loss == 0.0
    assert report.random_loss > 0 and report.random_agreement < 0.5
    assert report.verdict == "laya"


def test_always_worst_laya_loses_to_random():
    report = run_eval(ChessGame(), FakeEngine(pick="d"))
    assert report.laya_loss > report.random_loss and report.verdict == "variety"


def test_too_few_samples_never_earn_a_laya_verdict():
    report = run_eval(ChessGame(), FakeEngine(pick="a"), positions=5)
    assert report.samples == 5 and report.verdict == "variety"


def test_failures_are_counted_not_scored():
    report = run_eval(ChessGame(), FakeEngine(usage={"truncated": True}), positions=5)
    assert report.samples == 0 and report.failures == 5 and report.verdict == "variety"


def test_report_renders_a_table_and_the_rule():
    report = run_eval(ChessGame(), FakeEngine(pick="a"))
    text = render_report([report], k=4, depth=1, seed=1, today=date(2026, 10, 9))
    assert "| chess | 30 |" in text and "Decision rule" in text and "2026-10-09" in text
