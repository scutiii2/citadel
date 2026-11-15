"""Stand-ins for the Portcullis test helpers the moved tests were written with.

In Portcullis a test logged in as an account; here the account is whatever uid
the request headers name, so "logging in" only switches those headers.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def uid_of(name: str) -> str:
    return f"uid-{name}"


def login(client: TestClient, username: str, password: str = "") -> None:
    client.headers.update({"X-Requester-Uid": uid_of(username), "X-Requester-Username": username,
                           "X-Requester-Email": f"{username}@example.com"})


def as_admin(client: TestClient) -> None:
    login(client, "root")


def make_member(client: TestClient, email=None, username: str = "alice", verify: bool = True) -> str:
    """Nothing to register: an account exists as soon as its uid is named."""
    return username


class _Uids:
    def __getitem__(self, name: str) -> str:
        return uid_of(name)


def uids(client: TestClient) -> _Uids:
    return _Uids()


def action_messages(client: TestClient) -> list[str]:
    """What Stronghold asked Portcullis to put on the Logs page."""
    return [message for _uid, _action, message in client.app.state.platform.actions]
