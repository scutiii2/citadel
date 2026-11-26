"""Reading a stored file: by its owner through Portcullis, or by a signed link."""
from urllib.parse import urlsplit

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from src import file_routes
from src.services.identity_context import IdentityContextMiddleware
from src.services.user_files.runtime import FilesRuntime
from src.services.user_files.service import Settings, chunks_of
from tests.auth_helpers import FreshHeaders, service_auth

ALICE = FreshHeaders(uid="account-alice", username="same-name")
BOB = FreshHeaders(uid="account-bob", username="same-name")


@pytest.fixture
def setup(monkeypatch, tmp_path):
    runtime = FilesRuntime(Settings(store_dir=tmp_path / "store", signing_key=b"x" * 32,
                                    public_base_url="http://testserver"))
    monkeypatch.setattr(file_routes.files_runtime, "get_runtime", lambda _: runtime)
    stored = runtime.call(runtime.files.upload("account-alice", "n.txt", chunks_of(b"hello")))
    app = Starlette()
    app.add_middleware(IdentityContextMiddleware)
    file_routes.install_file_routes(app)
    try:
        with TestClient(app) as client:
            yield client, runtime.files, stored
    finally:
        runtime.close()


def test_content_is_streamed_to_its_owner_only(setup):
    client, _, stored = setup
    path = f"/files/{stored.file_id}/content"
    response = client.get(path, headers=ALICE)
    assert response.content == b"hello" and response.headers["content-security-policy"] == "sandbox"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get(path, headers=BOB).status_code == 404
    assert client.get(path).status_code == 401


def test_signed_link_downloads_an_attachment_and_a_forged_one_does_not(setup):
    client, files, stored = setup
    client.auth = service_auth()
    url = urlsplit(files.download_url(stored))
    response = client.get(f"{url.path}?{url.query}")
    assert response.content == b"hello" and response.headers["content-disposition"].startswith("attachment;")
    for query in ("", "?exp=bad&sig=x", "?exp=2000000000&sig=forged"):
        assert client.get(url.path + query).status_code == 404
