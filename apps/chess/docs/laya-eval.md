# Laya eval

Date: 2026-10-16. Model: `convaiinnovations/laya`. Candidates per position: 4. Engine depth: 2. Seed: 1.

Laya chose among the engine's top candidates. Loss is the engine score gap to the best candidate (chess in pawns, Tetris in heuristic points, each gap capped at 20 so a forced mate cannot dominate); lower is better. The random baseline is the exact expectation of a uniform pick from the same candidates.

| Game | Samples | Failed | Laya picks best | Random picks best | Laya loss | Random loss | Latency (s) | Verdict |
|---|---|---|---|---|---|---|---|---|
| chess | 60 | 0 | 47% | 25% | 0.480 | 1.230 | 0.46 | laya |
| tetris | 60 | 0 | 42% | 25% | 0.439 | 0.591 | 0.49 | laya |

Decision rule: Laya becomes a game's default picker only with at least 30 samples and a mean loss at most 75% of the random baseline's. Otherwise the default is `variety`.
These are positions from random play, not a held-out benchmark of real games.
