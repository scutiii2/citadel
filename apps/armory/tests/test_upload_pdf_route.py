"""Uploads go to the shared store, whichever capabilities are on, under the stable account id."""
import asyncio
import io

import pytest
from PIL import Image
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.testclient import TestClient

from src import upload_routes
from src.services.file_errors import ErrorCode, FileError
from src.services.identity_context import IdentityContextMiddleware
from src.services.user_files.runtime import FilesRuntime
from src.services.user_files.service import Settings
from tests.auth_helpers import FreshHeaders

HEADERS = FreshHeaders(uid="account-alice", username="alice")
MB = 1024 * 1024


@pytest.fixture
def setup(monkeypatch, tmp_path):
    runtime = FilesRuntime(Settings(store_dir=tmp_path / "store", signing_key=b"x" * 32))
    monkeypatch.setattr(upload_routes.files_runtime, "get_runtime", lambda _: runtime)
    app = Starlette()
    app.add_middleware(IdentityContextMiddleware)
    upload_routes.install_upload_routes(app)
    try:
        with TestClient(app) as client:
            yield client, runtime.files
    finally:
        runtime.close()


def post(client, name, content, path="/upload/file", headers=HEADERS):
    return client.post(path, headers=headers, files={"file": (name, content)})


def png():
    stream = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(stream, format="PNG")
    return stream.getvalue()


def test_any_accepted_file_is_kept_for_its_owner_under_a_bare_name(setup):
    client, files = setup
    body = post(client, "C:\\docs\\notes.md", b"# hi").json()
    assert (body["name"], body["kind"], body["pages"], body["size"]) == ("notes.md", "text", 0, 4)
    assert [f.file_id for f in files.list("account-alice")] == [body["file_id"]]


def test_the_pdf_alias_takes_pdf_and_images_only(setup):
    client, files = setup
    assert post(client, "p.png", png(), "/upload/pdf").json()["kind"] == "image"
    refused = post(client, "notes.md", b"# hi", "/upload/pdf")
    assert refused.status_code == 400 and "PDF or an image" in refused.json()["error"]
    assert len(files.list("account-alice")) == 1


@pytest.mark.parametrize("headers, status", [({}, 401), (FreshHeaders(invalid=True), 401), (FreshHeaders(), 400)])
def test_token_and_stable_identity_required(setup, headers, status):
    client, files = setup
    assert post(client, "n.txt", b"x", headers=headers).status_code == status
    assert files.list("account-alice") == []


def test_size_limits_depend_on_the_kind_and_bad_uploads_say_why(setup):
    client, files = setup
    assert client.post("/upload/file", headers=HEADERS).status_code == 400
    assert post(client, "n.txt", b"x" * (15 * MB + 1)).status_code == 413
    assert post(client, "a.mp3", b"x" * (15 * MB + 1)).status_code == 200
    assert post(client, "a.mp3", b"x" * (20 * MB + 1)).status_code == 413
    assert post(client, "run.exe", b"MZ\x00").status_code == 400
    assert [f.kind for f in files.list("account-alice")] == ["audio"]


def test_body_limit_stops_reading_before_multipart_finishes(setup):
    from src.citadel_auth import Caller, requester_context
    from tests import auth_helpers
    _, files = setup
    received = 0

    async def receive():
        nonlocal received
        received += 1
        prefix = b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="x.pdf"\r\n\r\n' if received == 1 else b''
        return {"type": "http.request", "body": prefix + b"x" * MB, "more_body": received < 32}

    headers = [(k.lower().encode(), v.encode()) for k, v in HEADERS.items()]
    headers.append((b"content-type", b"multipart/form-data; boundary=boundary"))
    request = Request({"type": "http", "method": "POST", "path": "/upload/file", "headers": headers}, receive=receive)

    async def invoke():
        async with requester_context(auth_helpers.stack["armory"], Caller("portcullis"),
                                     HEADERS["X-Citadel-Requester"], "armory"):
            return await upload_routes.upload_any(request)

    assert asyncio.run(invoke()).status_code == 413
    assert received < 32
    assert files.list("account-alice") == []


@pytest.mark.parametrize("error, status, message", [
    (FileError(ErrorCode.CORRUPT_FILE, "Not a valid PDF"), 400, "Not a valid PDF"),
    (FileError(ErrorCode.INTERNAL, "/private/store/internal"), 503, "File storage is unavailable"),
    (OSError("/private/store/internal"), 503, "File storage is unavailable"),
])
def test_errors_hide_unexpected_details(setup, monkeypatch, error, status, message):
    client, _ = setup

    def fail(*_):
        raise error

    monkeypatch.setattr(upload_routes, "_keep", fail)
    response = post(client, "n.txt", b"x")
    assert response.status_code == status
    assert response.json() == {"error": message}
