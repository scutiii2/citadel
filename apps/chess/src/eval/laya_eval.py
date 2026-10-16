"""Does Laya pick better candidate moves than chance? Run manually:

    python -m src.eval.laya_eval [--positions N] [--k K] [--depth D] [--seed S] [--out PATH]

Needs the real model (`pip install -e ".[laya]"`). Not part of the test suite.
For each sampled position it asks Laya to choose among the engine's top k
candidates and compares the engine score of the chosen move with the best one
and with a uniformly random pick from the same candidates.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from src.games.base import Game
from src.games.registry import build_games
from src.opponent.laya_client import DEFAULT_MODEL, LayaClient, LayaError
from src.opponent.laya_picker import INSTRUCTIONS

OUT_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "laya-eval.md"
MIN_SAMPLES = 30
LOSS_RATIO = 0.75  # Laya must lose at most this share of what a random pick loses
LOSS_CAP = 20.0  # a forced mate scores +-10000; cap each gap so one position cannot dominate the mean


@dataclass(frozen=True)
class GameReport:
    game: str
    samples: int
    failures: int
    laya_agreement: float  # share of positions where Laya chose the engine's best move
    random_agreement: float
    laya_loss: float  # mean score gap to the best candidate
    random_loss: float
    mean_latency: float
    verdict: str  # "laya" or "variety"


def sample_states(game: Game, count: int, rng: random.Random) -> list[Any]:
    """Unfinished positions reached by random legal play from the start."""
    states: list[Any] = []
    attempts = 0
    while len(states) < count and attempts < count * 20:
        attempts += 1
        state = game.new_state({})
        for _ in range(rng.randint(2, 24)):
            moves = game.legal_moves(state)
            if not moves or game.status(state).finished:
                break
            state = game.apply(state, rng.choice(moves))
        if not game.status(state).finished and game.side_to_move(state) is not None:
            states.append(state)
    return states


def _gap(best: float, score: float) -> float:
    return min(best - score, LOSS_CAP)


async def evaluate_game(game: Game, client: LayaClient, positions: int, k: int, depth: int, seed: int) -> GameReport:
    rng = random.Random(f"{game.id}:{seed}")
    agree = random_agree = failures = scored = 0
    laya_loss = random_loss = latency = 0.0
    for state in sample_states(game, positions * 2, rng):  # spare positions cover ones with a single candidate
        if scored + failures == positions:
            break
        cands = game.candidates(state, k, depth, 5.0)
        if len(cands) < 2:
            continue
        keys = [chr(ord("a") + i) for i in range(len(cands))]
        options = {key: game.summarize(state, c) for key, c in zip(keys, cands)}
        started = time.monotonic()
        try:
            choice = await client.choose(game.describe_position(state), INSTRUCTIONS, options)
        except LayaError:
            failures += 1
            continue
        latency += time.monotonic() - started
        best = cands[0].score
        chosen = keys.index(choice.key)
        scored += 1
        agree += chosen == 0
        laya_loss += _gap(best, cands[chosen].score)
        random_agree += 1 / len(cands)
        random_loss += sum(_gap(best, c.score) for c in cands) / len(cands)
    if scored == 0:
        return GameReport(game.id, 0, failures, 0.0, 0.0, 0.0, 0.0, 0.0, "variety")
    report = GameReport(
        game.id, scored, failures, agree / scored, random_agree / scored,
        laya_loss / scored, random_loss / scored, latency / scored, "variety",
    )
    better = scored >= MIN_SAMPLES and report.laya_loss <= LOSS_RATIO * report.random_loss
    return GameReport(**{**report.__dict__, "verdict": "laya" if better else "variety"})


def render_report(reports: list[GameReport], k: int, depth: int, seed: int, today: date) -> str:
    lines = [
        "# Laya eval", "",
        f"Date: {today.isoformat()}. Model: `{DEFAULT_MODEL}`. Candidates per position: {k}. "
        f"Engine depth: {depth}. Seed: {seed}.", "",
        "Laya chose among the engine's top candidates. Loss is the engine score gap to the best "
        "candidate (chess in pawns, Tetris in heuristic points, each gap capped at 20 so a forced mate "
        "cannot dominate); lower is better. The random baseline "
        "is the exact expectation of a uniform pick from the same candidates.", "",
        "| Game | Samples | Failed | Laya picks best | Random picks best | Laya loss | Random loss | Latency (s) | Verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        lines.append(
            f"| {r.game} | {r.samples} | {r.failures} | {r.laya_agreement:.0%} | {r.random_agreement:.0%} | "
            f"{r.laya_loss:.3f} | {r.random_loss:.3f} | {r.mean_latency:.2f} | {r.verdict} |"
        )
    lines += [
        "", f"Decision rule: Laya becomes a game's default picker only with at least {MIN_SAMPLES} samples "
        f"and a mean loss at most {LOSS_RATIO:.0%} of the random baseline's. Otherwise the default is `variety`.",
        "These are positions from random play, not a held-out benchmark of real games.", "",
    ]
    return "\n".join(lines)


async def run(positions: int, k: int, depth: int, seed: int, out: Path) -> str:
    client = LayaClient(timeout=30.0)
    if not client.is_available():
        raise SystemExit('Laya is not installed: pip install -e ".[laya]"')
    client.prepare()
    reports = [await evaluate_game(game, client, positions, k, depth, seed) for game in build_games().values()]
    text = render_report(reports, k, depth, seed, date.today())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--positions", type=int, default=60)
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()
    print(asyncio.run(run(args.positions, args.k, args.depth, args.seed, args.out)))


if __name__ == "__main__":
    main()
