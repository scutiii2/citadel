import base64
from src.sessions import GameSessions


class Clock:
    def __init__(self):
        self.now = 0.0
    def __call__(self):
        return self.now


def test_open_resolves_owner_and_unknown_token_is_absent():
    sessions = GameSessions(60)
    token = sessions.open("42")
    assert sessions.owner_of(token) == "42"
    assert sessions.owner_of("unknown") is None
    assert len(base64.urlsafe_b64decode(token + "=")) == 32
    assert sessions.open("42") != token


def test_expiry_is_not_refreshed_by_lookup():
    clock = Clock()
    sessions = GameSessions(60, clock=clock)
    token = sessions.open("42")
    clock.now = 59
    assert sessions.owner_of(token) == "42"
    clock.now = 60
    assert sessions.owner_of(token) is None


def test_capacity_evicts_oldest_not_least_recently_read():
    sessions = GameSessions(60, max_sessions=2)
    first = sessions.open("first")
    second = sessions.open("second")
    assert sessions.owner_of(first) == "first"
    third = sessions.open("third")
    assert sessions.owner_of(first) is None
    assert sessions.owner_of(second) == "second"
    assert sessions.owner_of(third) == "third"


def test_instances_do_not_share_sessions():
    first, second = GameSessions(60), GameSessions(60)
    assert second.owner_of(first.open("42")) is None
