from src.services.permissions import (ALL_PERMISSIONS, CHAT_USE, GAMES_MANAGE,
    game_play_permission, is_known_permission, permission_description)


def test_game_play_permission_name():
    assert game_play_permission("ascension") == "games.ascension.play"


def test_known_permissions():
    for name in (CHAT_USE, "games.ascension.play", GAMES_MANAGE, "games.a" + "-" * 62 + ".play"):
        assert is_known_permission(name)
    for name in ("games..play", "games.Bad.play", "games.a/b.play", "games.x.manage", "ascension.play", "games.-x.play", "games.a.play\n", "games." + "a" * 64 + ".play"):
        assert not is_known_permission(name), name


def test_descriptions():
    assert permission_description(CHAT_USE) == ALL_PERMISSIONS[CHAT_USE]
    assert permission_description("games.ascension.play") == "Play ascension"
    assert permission_description("nope") is None
