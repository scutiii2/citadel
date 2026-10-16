import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.games.registry import build_games
from src.opponent.engine_picker import EnginePicker
from src.opponent.variety_picker import VarietyPicker
from src.sessions import SessionStore

TOKEN = "t0ken"
ANN = {"X-Internal-Token": TOKEN, "X-Requester-Username": "ann"}
BOB = {"X-Internal-Token": TOKEN, "X-Requester-Username": "bob"}


@pytest.fixture
def client(config):
    games = build_games()
    store = SessionStore(games, {"engine": EnginePicker(), "variety": VarietyPicker()}, config)
    return TestClient(create_app(store, games, TOKEN))


def new_game(client, headers=ANN, **body):
    body = {"game": "chess", "difficulty": "easy", "picker": "engine", **body}
    return client.post("/sessions", json=body, headers=headers)


def test_health_needs_no_token(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-Requester-Username": "ann"}, {"X-Internal-Token": "wrong", "X-Requester-Username": "ann"}])
def test_token_is_required(client, headers):
    assert client.get("/games", headers=headers).status_code == 401


def test_requester_header_is_required(client):
    response = client.get("/games", headers={"X-Internal-Token": TOKEN})
    assert response.status_code == 400 and "X-Requester-Username" in response.json()["error"]


def test_list_games(client):
    games = client.get("/games", headers=ANN).json()["games"]
    assert [g["id"] for g in games] == ["chess", "tetris"]
    assert "player_side" in games[0]["options"]


def test_create_session_returns_the_view(client):
    response = new_game(client)
    assert response.status_code == 201
    body = response.json()
    assert body["game"] == "chess" and body["turn"] == "player" and len(body["state"]["legal_moves"]) == 20


def test_full_chess_exchange(client):
    sid = new_game(client).json()["id"]
    moved = client.post(f"/sessions/{sid}/moves", json={"move": {"uci": "e2e4"}}, headers=ANN)
    assert moved.status_code == 200 and moved.json()["turn"] == "bot"
    bot = client.post(f"/sessions/{sid}/bot-move", headers=ANN).json()
    assert bot["turn"] == "player" and bot["bot_move"]["by"] == "bot" and len(bot["history"]) == 2
    assert client.get(f"/sessions/{sid}", headers=ANN).json()["history"] == bot["history"]


def test_tetris_session(client):
    sid = new_game(client, game="tetris", options={"seed": 3, "piece_limit": 5}).json()["id"]
    moved = client.post(f"/sessions/{sid}/moves", json={"move": {"rotation": 0, "column": 0}}, headers=ANN)
    assert moved.status_code == 200 and moved.json()["state"]["placed"] == {"player": 1, "bot": 0}


def test_error_statuses(client):
    sid = new_game(client).json()["id"]
    assert client.post(f"/sessions/{sid}/moves", json={"move": {"uci": "e2e5"}}, headers=ANN).status_code == 400
    assert client.post(f"/sessions/{sid}/bot-move", headers=ANN).status_code == 409  # not the bot's turn
    assert new_game(client, game="go").status_code == 400
    assert new_game(client, difficulty="godlike").status_code == 400
    assert client.post("/sessions", json={"nope": 1}, headers=ANN).status_code == 400
    assert client.get("/sessions/missing", headers=ANN).status_code == 404


def test_other_users_cannot_see_or_touch_a_session(client):
    sid = new_game(client).json()["id"]
    assert client.get(f"/sessions/{sid}", headers=BOB).status_code == 404
    assert client.post(f"/sessions/{sid}/moves", json={"move": {"uci": "e2e4"}}, headers=BOB).status_code == 404
    assert client.delete(f"/sessions/{sid}", headers=BOB).status_code == 404


def test_delete_ends_the_session(client):
    sid = new_game(client).json()["id"]
    assert client.delete(f"/sessions/{sid}", headers=ANN).status_code == 204
    assert client.get(f"/sessions/{sid}", headers=ANN).status_code == 404


def test_session_cap_returns_409(client):
    for _ in range(5):
        assert new_game(client).status_code == 201
    assert new_game(client).status_code == 409
