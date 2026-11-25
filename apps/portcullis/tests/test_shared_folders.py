"""Temporary shared folders: the owner's routes, the public link, and the rules that keep both safe."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import update

from src.db import utcnow
from src.models import SharedFolder
from src.services import shared_folder_service as svc
from src.services.public_rate_limiter import PublicReadLimiter
from src.services.shared_folder_service import SharedFolderService, clean_file_name
from tests.test_admin import login, make_member
from tests.test_registration import as_admin

TOKEN_MISSING = "x" * 43


def open_folder(client: TestClient, **body) -> dict:
    response = client.post("/api/shared-folders", json={"name": "Trip", "minutes": 30, **body})
    assert response.status_code == 201, response.text
    return response.json()


def put(client: TestClient, token: str, data: bytes = b"hello", name: str = "a.txt"):
    return client.put(f"/api/folder-links/{token}/files", params={"name": name}, content=data)


def guest(client: TestClient) -> TestClient:
    client.post("/api/auth/logout", json={})
    return client


def expire(client: TestClient, folder_id: int) -> None:
    async def run() -> None:
        async with client.app.state.database.sessions() as session:
            await session.execute(
                update(SharedFolder).where(SharedFolder.id == folder_id).values(expires_at=utcnow() - timedelta(seconds=1)))
            await session.commit()

    client.portal.call(run)


def root(client: TestClient) -> Path:
    return client.app.state.settings.database_path.parent / "shared_folders"


def test_owner_opens_a_folder_and_a_guest_adds_and_downloads_without_login(client: TestClient) -> None:
    as_admin(client)
    folder = open_folder(client)
    guest(client)

    added = put(client, folder["token"], b"hello world", "../notes.txt")
    assert added.status_code == 201 and added.json()["name"] == "notes.txt" and added.json()["size"] == 11
    seen = client.get(f"/api/folder-links/{folder['token']}").json()
    assert seen["name"] == "Trip" and [f["name"] for f in seen["files"]] == ["notes.txt"]
    assert "token" not in seen and seen["max_file_bytes"] == svc.MAX_FILE_BYTES
    download = client.get(f"/api/folder-links/{folder['token']}/files/{added.json()['id']}")
    assert download.content == b"hello world"
    assert download.headers["content-type"] == "application/octet-stream"
    assert download.headers["content-disposition"].startswith("attachment")
    assert download.headers["x-content-type-options"] == "nosniff"


def test_guests_cannot_remove_anything_and_only_the_owner_can(client: TestClient) -> None:
    as_admin(client)
    folder = open_folder(client)
    file_id = put(client, folder["token"]).json()["id"]
    guest(client)

    assert client.delete(f"/api/folder-links/{folder['token']}/files/{file_id}").status_code == 405
    assert client.delete(f"/api/shared-folders/{folder['id']}/files/{file_id}").status_code == 401
    assert client.delete(f"/api/shared-folders/{folder['id']}").status_code == 401

    as_admin(client)
    assert client.delete(f"/api/shared-folders/{folder['id']}/files/{file_id}").status_code == 204
    assert client.get("/api/shared-folders").json()[0]["files"] == []
    assert not (root(client) / str(folder["id"]) / str(file_id)).exists()


def test_another_account_cannot_touch_a_folder_it_does_not_own(client: TestClient, email) -> None:
    as_admin(client)
    folder = open_folder(client)
    guest(client)
    make_member(client, email, "bob")
    login(client, "bob")

    assert client.delete(f"/api/shared-folders/{folder['id']}").status_code == 404
    assert client.get("/api/shared-folders").json() == []


def test_owner_delete_ends_the_link_and_wipes_the_files(client: TestClient) -> None:
    as_admin(client)
    folder = open_folder(client)
    put(client, folder["token"])
    assert (root(client) / str(folder["id"])).is_dir()

    assert client.delete(f"/api/shared-folders/{folder['id']}").status_code == 204

    assert client.get(f"/api/folder-links/{folder['token']}").status_code == 404
    assert not (root(client) / str(folder["id"])).exists()


def test_deadline_is_fixed_at_creation_and_never_moves(client: TestClient) -> None:
    as_admin(client)
    folder = open_folder(client, minutes=10)
    file_id = put(client, folder["token"]).json()["id"]
    client.delete(f"/api/shared-folders/{folder['id']}/files/{file_id}")
    put(client, folder["token"])

    assert client.get("/api/shared-folders").json()[0]["expires_at"] == folder["expires_at"]


def test_an_expired_folder_reads_as_missing_before_the_sweeper_runs_then_is_swept(client: TestClient) -> None:
    as_admin(client)
    folder = open_folder(client)
    put(client, folder["token"])
    expire(client, folder["id"])

    assert client.get(f"/api/folder-links/{folder['token']}").status_code == 404
    assert put(client, folder["token"]).status_code == 404
    assert client.get("/api/shared-folders").json() == []

    async def sweep() -> int:
        async with client.app.state.database.sessions() as session:
            return await SharedFolderService(session, root(client)).purge_expired()

    assert client.portal.call(sweep) == 1
    assert not (root(client) / str(folder["id"])).exists()


def test_the_lifetime_is_at_most_one_hour(client: TestClient) -> None:
    as_admin(client)
    assert client.post("/api/shared-folders", json={"name": "x", "minutes": 61}).status_code == 422
    assert client.post("/api/shared-folders", json={"name": "x", "minutes": 0}).status_code == 422


def test_three_folders_at_a_time(client: TestClient) -> None:
    as_admin(client)
    for _ in range(svc.MAX_OPEN_FOLDERS):
        open_folder(client)
    assert client.post("/api/shared-folders", json={"name": "x", "minutes": 5}).status_code == 409


def test_file_size_cap_leaves_nothing_behind(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(svc, "MAX_FILE_BYTES", 10)
    as_admin(client)
    folder = open_folder(client)

    assert put(client, folder["token"], b"x" * 11).status_code == 413
    assert put(client, folder["token"], b"x" * 10).status_code == 201
    names = [p.name for p in (root(client) / str(folder["id"])).iterdir()]
    assert len(names) == 1 and not names[0].startswith(".part")


def test_folder_caps_on_files_and_bytes(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(svc, "MAX_FOLDER_FILES", 2)
    monkeypatch.setattr(svc, "MAX_FOLDER_BYTES", 10)
    as_admin(client)
    folder = open_folder(client)

    assert put(client, folder["token"], b"x" * 6).status_code == 201
    assert put(client, folder["token"], b"x" * 6).status_code == 409  # folder full
    assert put(client, folder["token"], b"x" * 4).status_code == 201
    assert put(client, folder["token"], b"x").status_code == 409  # two files already


def test_empty_upload_and_odd_links_are_refused(client: TestClient) -> None:
    as_admin(client)
    folder = open_folder(client)

    assert put(client, folder["token"], b"").status_code == 409
    assert client.get(f"/api/folder-links/{TOKEN_MISSING}").status_code == 404
    assert client.get("/api/folder-links/short").status_code == 404


def test_public_reads_are_rate_limited_per_address(client: TestClient) -> None:
    client.app.state.share_limiter = PublicReadLimiter(max_requests=2)
    assert client.get(f"/api/folder-links/{TOKEN_MISSING}").status_code == 404
    assert client.get(f"/api/folder-links/{TOKEN_MISSING}").status_code == 404
    assert client.get(f"/api/folder-links/{TOKEN_MISSING}").status_code == 429


def test_the_owner_routes_need_a_login(client: TestClient) -> None:
    assert client.get("/api/shared-folders").status_code == 401
    assert client.post("/api/shared-folders", json={"name": "x", "minutes": 5}).status_code == 401


def test_file_names_are_cut_to_a_plain_name() -> None:
    assert clean_file_name("..\\..\\etc/passwd") == "passwd"
    assert clean_file_name(".hidden") == "hidden"
    assert clean_file_name("a\x00b\nc.txt") == "abc.txt"
    assert clean_file_name("///") == "file"
    assert len(clean_file_name("n" * 500)) == svc.NAME_LENGTH
