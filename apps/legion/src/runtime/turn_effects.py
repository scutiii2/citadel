"""Whether a turn has run a tool that may change something, so it cannot safely be run again from the start.

`agent_config.run_chat` binds this once per turn. `ToolRound` marks it when it runs a tool that is not a known
read-only built-in (including a call to another agent). A turn that failed on its last gateway of one protocol is
rerun on the next protocol only while nothing is marked.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_state: ContextVar[list[bool] | None] = ContextVar("turn_effects", default=None)


def bind() -> Token:
    return _state.set([False])


def reset(token: Token) -> None:
    _state.reset(token)


def mark() -> None:
    state = _state.get()
    if state is not None:
        state[0] = True


def happened() -> bool:
    state = _state.get()
    return bool(state and state[0])
