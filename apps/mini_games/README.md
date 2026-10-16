# mini_games

Game backend for Ember: chess and Tetris against a bot, over HTTP. It holds the
game engines, the opponent and the per-user game sessions. It never calls an LLM,
so a game costs nothing. Spec:
`docs/superpowers/specs/2026-10-09-mini-games-backend-design.md` (repo root).

Part 1 of 3. The `ember_api` proxy with the `ember_web` page, and the MCP
extension tools for starting a game from chat, come in later specs.

## How the bot plays

1. The game engine finds and scores the best moves (`k` of them, set by the
   difficulty).
2. A picker chooses one:
   - `engine` - always the best move.
   - `variety` - a weighted random pick among the top moves; no model.
   - `laya` - the local Laya model reads a short text summary of the position
     and one line per candidate and picks one. If Laya is uncertain, missing,
     slow or wrong, the engine's best move is used, so a turn never fails.
3. `configs/config_app.json` sets the default picker per game and the
   difficulty table. `docs/laya-eval.md` records whether Laya beat random choice
   and therefore which default was chosen.

Laya reads text only (512-token window); it cannot read a board, which is why
the engine proposes the candidates.

## Games

| Id | Notes |
|---|---|
| `chess` | `python-chess` rules, alpha-beta search. Option `player_side`: `white` or `black`. |
| `tetris` | Versus race on the same seeded pieces, in lockstep: the player places piece n, then the bot places piece n. Options `seed`, `piece_limit` (5 to 200, default 40). No garbage lines yet. |

A game is one plugin file in `src/games/` implementing the `Game` protocol in
`src/games/base.py`, plus a line in `src/games/registry.py`.

## Requirements

- Python 3.11 or newer on Windows (`py` launcher).
- Optional: the `laya` package for the Laya picker (`pip install -e ".[laya]"`).

## Run

```
run.bat
```

The first start creates `.venv_mini_games`, installs the project, and creates
`configs/config_app.json` and `.env` from their `.example` twins. Both
real files are gitignored. Put the same `INTERNAL_API_TOKEN` in `.env`
that `mcp_server`, `ai_agent` and `ember_api` use; once it is set, every route
except `/health` needs the `X-Internal-Token` header.

`server_launcher` lists this project from its `run.bat`.

## API

All routes except `/health` need `X-Internal-Token` (once configured) and
`X-Requester-Username`, the session owner.

| Route | Purpose |
|---|---|
| `GET /health` | Liveness, no auth |
| `GET /games` | Game ids and their option schemas |
| `POST /sessions` | Body `{"game", "options", "difficulty", "picker"}`; returns the session view |
| `GET /sessions/{id}` | Current state, turn, status and history |
| `POST /sessions/{id}/moves` | Body `{"move": {...}}`; the player's move |
| `POST /sessions/{id}/bot-move` | The bot picks and plays; the view gains `bot_move` |
| `DELETE /sessions/{id}` | End the session |

Moves: chess `{"uci": "e2e4"}`; Tetris `{"rotation": 0, "column": 3}` (`column` is
the leftmost column of the rotated piece).

Errors: 400 bad move, body, option or game; 401 bad token; 404 unknown or someone
else's session; 409 wrong turn, game over, or too many sessions. The `turn` field
of a session view is `player`, `bot` or `null` (finished). When the bot moves
first (chess with `player_side` black), call `bot-move` right after creating.

Sessions live in memory only: a restart ends all games, and idle sessions expire
(`session_ttl_seconds`). Each user may hold `max_sessions_per_user`.

## Tests and the Laya eval

```
.venv_mini_games\Scripts\python -m pytest
.venv_mini_games\Scripts\python -m src.eval.laya_eval
```

The tests use a fake Laya engine. The eval needs the real model and is run by
hand; it writes `docs/laya-eval.md`.

## Layout

- `src/games/` - game protocol, chess, Tetris and the registry.
- `src/opponent/` - the Laya client and the three pickers.
- `src/sessions.py` - sessions, locks, turn checks, expiry.
- `src/api.py`, `src/run.py` - HTTP app and entry point.
- `src/eval/` - the Laya evaluation harness.
- `configs/` - gitignored real config with a committed `.example` twin.
- `.env` - gitignored real credentials with a committed `.env.example` twin.
