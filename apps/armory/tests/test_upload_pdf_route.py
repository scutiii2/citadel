"""Native uploads reuse the Ember endpoint and require stable account identity."""
from types import SimpleNamespace
from unittest.mock import Mock
import sys

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from src import upload_routes
from src.services import capability_registry
from src.services.identity_context import IdentityContextMiddleware, current_uid
from src.capabilities.pdf_merger.utils.errors import ErrorCode, MergerError

HEADERS = {"X-Internal-Token": "shared", "X-Requester-UID": "account-alice", "X-Requester-Username": "alice"}
FILE = {"file_id": "f_1", "name": "scan.pdf", "pages": 2, "kind": "pdf", "size": 12, "expires_at": 2000000000}

class PdfError(Exception):
    pass

@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(upload_routes, "settings", SimpleNamespace(internal_api_token="shared"))
    monkeypatch.setattr(capability_registry, "is_enabled", lambda _: True)
    identities = []
    def save(name, content):
        identities.append(current_uid())
        return SimpleNamespace(model_dump=lambda **_: FILE)
    upload = Mock(side_effect=save)
    domain = SimpleNamespace(upload=upload, PdfError=PdfError)
    monkeypatch.setitem(sys.modules, "src.capabilities.pdf_merger.domain", domain)
    import src.capabilities.pdf_merger as package
    monkeypatch.setattr(package, "domain", domain, raising=False)
    app = Starlette()
    app.add_middleware(IdentityContextMiddleware)
    upload_routes.install_upload_routes(app)
    with TestClient(app) as client:
        yield client, upload, identities


def post(client, headers=HEADERS, filename="C:\\docs\\scan.pdf", content=b"%PDF-original"):
    return client.post("/upload/pdf", headers=headers, files={"file": (filename, content)})


def test_original_bytes_and_authenticated_uid_cross_thread_boundary(setup):
    client, upload, identities = setup
    response = post(client)
    assert response.status_code == 200 and response.json() == FILE
    upload.assert_called_once_with("scan.pdf", b"%PDF-original")
    assert identities == ["account-alice"]


@pytest.mark.parametrize("headers, status", [({}, 401), ({"X-Internal-Token": "bad"}, 401), ({"X-Internal-Token": "shared", "X-Requester-Username": "alice"}, 400)])
def test_token_and_stable_identity_required(setup, headers, status):
    client, upload, _ = setup
    assert post(client, headers=headers).status_code == status
    upload.assert_not_called()


@pytest.mark.parametrize("registered", [False, None])
def test_disabled_or_absent_capability_fails_closed(setup, monkeypatch, registered):
    client, upload, _ = setup
    def enabled(_):
        if registered is None:
            raise KeyError("absent")
        return registered
    monkeypatch.setattr(capability_registry, "is_enabled", enabled)
    assert post(client).status_code == 503
    upload.assert_not_called()


def test_limit_and_missing_file(setup):
    client, upload, _ = setup
    assert client.post("/upload/pdf", headers=HEADERS).status_code == 400
    assert post(client, content=b"x" * (15 * 1024 * 1024 + 1)).status_code == 413
    upload.assert_not_called()


def test_body_limit_stops_reading_before_multipart_finishes(setup):
    import asyncio
    from starlette.requests import Request
    _, upload, _ = setup
    received = 0
    async def receive():
        nonlocal received
        received += 1
        prefix = b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="x.pdf"\r\n\r\n' if received == 1 else b''
        return {"type": "http.request", "body": prefix + b"x" * (1024 * 1024), "more_body": received < 32}
    headers = [(k.lower().encode(), v.encode()) for k, v in HEADERS.items()]
    headers.append((b"content-type", b"multipart/form-data; boundary=boundary"))
    request = Request({"type": "http", "method": "POST", "path": "/upload/pdf", "headers": headers}, receive=receive)
    response = asyncio.run(upload_routes.upload_pdf(request))
    assert response.status_code == 413
    assert received < 32
    upload.assert_not_called()


@pytest.mark.parametrize("error, status, message", [
    (MergerError(ErrorCode.CORRUPT_FILE, "Not a valid PDF"), 400, "Not a valid PDF"),
    (PdfError("Account unavailable"), 400, "Account unavailable"),
    (MergerError(ErrorCode.INTERNAL, "/private/store/internal"), 503, "PDF capability is unavailable"),
    (OSError("/private/store/internal"), 503, "PDF capability is unavailable"),
])
def test_errors_hide_unexpected_details(setup, error, status, message):
    client, upload, _ = setup
    upload.side_effect = error
    response = post(client)
    assert response.status_code == status
    assert response.json() == {"error": message}
