import asyncio

import pytest

from src.games.base import GameError, IllegalMove, InvalidOptions
from src.games.registry import build_games
from src.opponent.engine_picker import EnginePicker
from src.opponent.variety_picker import VarietyPicker
from src.sessions import GameOver, SessionLimit, SessionNotFound, SessionStore, WrongTurn


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(config, clock):
    pickers = {"engine": EnginePicker(), "variety": VarietyPicker()}
    return SessionStore(build_games(), pickers, config, clock)


def run(coro):
    return asyncio.run(coro)


def create(store, owner="ann", game="chess", options=None, difficulty="easy", picker="engine"):
    return run(store.create(owner, game, options or {}, difficulty, picker))


def test_create_uses_the_default_picker_and_assigns_sides(store):
    session = run(store.create("ann", "chess", {"player_side": "black"}, "easy", None))
    assert (session.player_side, session.bot_side, session.picker) == ("black", "white", "variety")
    view = store.view(session)
    assert view["turn"] == "bot" and view["status"]["finished"] is False


@pytest.mark.parametrize("args", [("go", {}, "easy", None), ("chess", {}, "godlike", None), ("chess", {}, "easy", "magic"), ("chess", {"x": 1}, "easy", None)])
def test_bad_create_arguments_are_rejected(store, args):
    with pytest.raises(InvalidOptions):
        run(store.create("ann", *args))


def test_player_then_bot_move(store):
    session = create(store)
    run(store.player_move("ann", session.id, {"uci": "e2e4"}))
    _, entry = run(store.bot_move("ann", session.id))
    assert entry["by"] == "bot" and entry["source"] == "engine"
    assert [h["by"] for h in session.history] == ["player", "bot"]
    assert store.view(session)["turn"] == "player"


def test_wrong_turn_is_rejected_and_state_is_unchanged(store):
    session = create(store)
    before = session.state
    with pytest.raises(WrongTurn):
        run(store.bot_move("ann", session.id))
    run(store.player_move("ann", session.id, {"uci": "e2e4"}))
    with pytest.raises(WrongTurn):
        run(store.player_move("ann", session.id, {"uci": "d2d4"}))
    assert session.state != before and len(session.history) == 1


def test_illegal_move_leaves_the_session_alone(store):
    session = create(store)
    with pytest.raises(IllegalMove):
        run(store.player_move("ann", session.id, {"uci": "e2e5"}))
    assert session.history == []


def test_finished_game_rejects_moves(store):
    session = create(store, game="tetris", options={"seed": 1, "piece_limit": 5})
    for _ in range(5):
        run(store.player_move("ann", session.id, {"rotation": 0, "column": 0}))
        run(store.bot_move("ann", session.id))
    assert store.view(session)["status"]["finished"] is True
    with pytest.raises(GameOver):
        run(store.player_move("ann", session.id, {"rotation": 0, "column": 0}))


def test_other_users_get_not_found(store):
    session = create(store)
    for call in (store.get, store.delete):
        with pytest.raises(SessionNotFound):
            run(call("bob", session.id))
    with pytest.raises(SessionNotFound):
        run(store.player_move("bob", session.id, {"uci": "e2e4"}))


def test_unknown_id_is_not_found(store):
    with pytest.raises(SessionNotFound):
        run(store.get("ann", "nope"))


def test_idle_sessions_expire(store, clock):
    session = create(store)
    clock.now += 3601
    with pytest.raises(SessionNotFound):
        run(store.get("ann", session.id))


def test_activity_keeps_a_session_alive(store, clock):
    session = create(store)
    clock.now += 3000
    run(store.get("ann", session.id))
    clock.now += 3000
    assert run(store.get("ann", session.id)) is session


def test_per_user_cap_and_delete_frees_a_slot(store):
    sessions = [create(store) for _ in range(5)]
    with pytest.raises(SessionLimit):
        create(store)
    create(store, owner="bob")  # other users are unaffected
    run(store.delete("ann", sessions[0].id))
    create(store)


def test_concurrent_moves_do_not_interleave(store):
    session = create(store)

    async def scenario():
        results = await asyncio.gather(
            store.player_move("ann", session.id, {"uci": "e2e4"}),
            store.player_move("ann", session.id, {"uci": "d2d4"}),
            return_exceptions=True,
        )
        return results

    results = run(scenario())
    assert sum(isinstance(r, WrongTurn) for r in results) == 1
    assert len(session.history) == 1


def test_a_picker_returning_an_illegal_move_is_reported(config, clock):
    class BadPicker:
        name = "bad"

        async def pick(self, game, state, difficulty):
            from src.opponent.base import Pick

            return Pick({"uci": "a1a8"}, "engine")

    store = SessionStore(build_games(), {"bad": BadPicker()}, config, clock)
    session = run(store.create("ann", "chess", {"player_side": "black"}, "easy", "bad"))
    with pytest.raises(GameError, match="illegal move"):
        run(store.bot_move("ann", session.id))


def test_view_names_the_winner_by_role(store):
    session = create(store, game="tetris", options={"seed": 1, "piece_limit": 5})
    session.state = type(session.state)(**{**session.state.__dict__, "topped_out": (True, False)})
    view = store.view(session)
    assert view["status"]["winner"] == "bot" and view["turn"] is None
