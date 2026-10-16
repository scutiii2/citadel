"""In-memory game sessions, owned by the asking user.

Every mutation holds the session's own lock, so a player move and a bot move
can never interleave, and two clients (the web page and the chat assistant)
can never both move at once. Idle sessions expire after a TTL; a per-user cap
bounds memory. A restart ends all games (no persistence in v1).
"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from src.config import AppConfig
from src.games.base import Game, GameError, IllegalMove, InvalidOptions, Move
from src.games.registry import get_game
from src.opponent.base import Picker


class SessionError(GameError):
    """Base for session-level failures."""


class SessionNotFound(SessionError):
    """Unknown id, expired, or owned by someone else."""


class WrongTurn(SessionError):
    """It is not that side's turn."""


class GameOver(SessionError):
    """The game has finished."""


class SessionLimit(SessionError):
    """The user already holds the maximum number of sessions."""


@dataclass
class Session:
    id: str
    owner: str
    game_id: str
    player_side: str
    bot_side: str
    state: Any
    picker: str
    difficulty: str
    created: float
    last_used: float
    history: list[dict[str, Any]] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SessionStore:
    def __init__(
        self,
        games: dict[str, Game],
        pickers: dict[str, Picker],
        config: AppConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._games, self._pickers, self._config, self._clock = games, pickers, config, clock
        self._sessions: dict[str, Session] = {}

    # -- lookup --------------------------------------------------------------------

    def _purge(self) -> None:
        cutoff = self._clock() - self._config.session_ttl_seconds
        for sid in [s.id for s in self._sessions.values() if s.last_used < cutoff and not s.lock.locked()]:
            del self._sessions[sid]

    def _find(self, owner: str, sid: str) -> Session:
        self._purge()
        session = self._sessions.get(sid)
        if session is None or session.owner != owner:
            raise SessionNotFound("no such game session")
        return session

    async def get(self, owner: str, sid: str) -> Session:
        session = self._find(owner, sid)
        session.last_used = self._clock()
        return session

    def count(self, owner: str) -> int:
        return sum(1 for s in self._sessions.values() if s.owner == owner)

    # -- lifecycle -----------------------------------------------------------------

    async def create(
        self, owner: str, game_id: str, options: dict[str, Any], difficulty: str, picker: str | None
    ) -> Session:
        self._purge()
        game = get_game(self._games, game_id)
        if difficulty not in self._config.difficulties:
            raise InvalidOptions(f"unknown difficulty {difficulty!r}; valid: {', '.join(self._config.difficulties)}")
        picker = picker or self._config.default_picker.get(game_id, "engine")
        if picker not in self._pickers:
            raise InvalidOptions(f"unknown picker {picker!r}; valid: {', '.join(self._pickers)}")
        if self.count(owner) >= self._config.max_sessions_per_user:
            raise SessionLimit(f"limit of {self._config.max_sessions_per_user} game sessions reached; delete one first")
        state = game.new_state(options)
        player, bot = game.assign_sides(options)
        now = self._clock()
        session = Session(secrets.token_urlsafe(9), owner, game_id, player, bot, state, picker, difficulty, now, now)
        self._sessions[session.id] = session
        return session

    async def delete(self, owner: str, sid: str) -> None:
        del self._sessions[self._find(owner, sid).id]

    # -- moves ---------------------------------------------------------------------

    def _check_turn(self, session: Session, game: Game, expected: str) -> None:
        turn = game.side_to_move(session.state)
        if turn is None:
            raise GameOver("the game is over")
        if turn != expected:
            raise WrongTurn(f"it is {turn}'s turn")

    async def player_move(self, owner: str, sid: str, move: Move) -> Session:
        session = self._find(owner, sid)
        game = self._games[session.game_id]
        async with session.lock:
            self._check_turn(session, game, session.player_side)
            session.state = game.apply(session.state, move)
            session.history.append({"side": session.player_side, "by": "player", "move": move})
            session.last_used = self._clock()
        return session

    async def bot_move(self, owner: str, sid: str) -> tuple[Session, dict[str, Any]]:
        session = self._find(owner, sid)
        game = self._games[session.game_id]
        async with session.lock:
            self._check_turn(session, game, session.bot_side)
            pick = await self._pickers[session.picker].pick(
                game, session.state, self._config.difficulties[session.difficulty]
            )
            try:
                session.state = game.apply(session.state, pick.move)
            except IllegalMove as error:  # a picker bug; never leave the game stuck silently
                raise GameError(f"the bot chose an illegal move: {error}") from error
            entry = {"side": session.bot_side, "by": "bot", "move": pick.move, "source": pick.source}
            session.history.append(entry)
            session.last_used = self._clock()
        return session, entry

    # -- presentation --------------------------------------------------------------

    def view(self, session: Session) -> dict[str, Any]:
        game = self._games[session.game_id]
        turn_side = game.side_to_move(session.state)
        status = game.status(session.state)
        role = None if turn_side is None else ("player" if turn_side == session.player_side else "bot")
        winner = None
        if status.winner is not None:
            winner = "player" if status.winner == session.player_side else "bot"
        return {
            "id": session.id,
            "game": session.game_id,
            "difficulty": session.difficulty,
            "picker": session.picker,
            "player_side": session.player_side,
            "bot_side": session.bot_side,
            "turn": role,
            "status": {"finished": status.finished, "winner": winner, "reason": status.reason},
            "state": game.to_dict(session.state),
            "history": list(session.history),
        }
