import pytest

from src.games.base import InvalidOptions
from src.games.registry import build_games, get_game


def test_registry_has_both_games():
    assert sorted(build_games()) == ["chess", "tetris"]


def test_get_game_returns_the_plugin():
    games = build_games()
    assert get_game(games, "chess").id == "chess"


@pytest.mark.parametrize("bad", ["go", None, 3])
def test_unknown_game_lists_the_valid_ones(bad):
    with pytest.raises(InvalidOptions, match="chess, tetris"):
        get_game(build_games(), bad)
