"""The native capability redeems signed download URLs without an internal token."""
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
from src import command_routes
from src.services import capability_registry
from src.capabilities.pdf_merger.utils.errors import ErrorCode, MergerError

class PdfError(Exception):
    pass

@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(capability_registry, "is_enabled", lambda _: True)
    path = tmp_path / "private-generated.pdf"
    path.write_bytes(b"%PDF-test")
    download = Mock(return_value=(path, "merged report.pdf"))
    domain = SimpleNamespace(download=download, PdfError=PdfError)
    monkeypatch.setitem(sys.modules, "src.capabilities.pdf_merger.domain", domain)
    import src.capabilities.pdf_merger as package
    monkeypatch.setattr(package, "domain", domain, raising=False)
    app = Starlette()
    command_routes.install_command_routes(app)
    with TestClient(app) as client:
        yield client, download


def test_signed_download_without_internal_token_is_secure_attachment(setup):
    client, download = setup
    response = client.get("/pdf/files/f_1/download?exp=2000000000&sig=signed")
    assert response.status_code == 200
    assert response.content == b"%PDF-test"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "merged%20report.pdf" in response.headers["content-disposition"]
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    download.assert_called_once_with("f_1", 2000000000, "signed")


@pytest.mark.parametrize("query", ["", "?exp=1", "?exp=bad&sig=signed", "?sig=signed", "?exp=1&sig="])
def test_missing_or_malformed_signatures_fail_closed(setup, query):
    client, download = setup
    response = client.get("/pdf/files/f_1/download" + query)
    assert response.status_code == 404
    assert response.json() == {"error": "File is not available"}
    download.assert_not_called()


@pytest.mark.parametrize("error", [PdfError("Signature invalid"), MergerError(ErrorCode.FILE_NOT_FOUND, "private missing identifier"), MergerError(ErrorCode.INVALID_REQUEST, "expired signature")])
def test_invalid_signature_and_missing_files_are_indistinguishable(setup, error):
    client, download = setup
    download.side_effect = error
    response = client.get("/pdf/files/f_1/download?exp=1&sig=signed")
    assert response.status_code == 404
    assert response.json() == {"error": "File is not available"}


@pytest.mark.parametrize("registered", [False, None])
def test_disabled_or_absent_capability_blocks_signed_download(setup, monkeypatch, registered):
    client, download = setup
    def enabled(_):
        if registered is None:
            raise KeyError("absent")
        return registered
    monkeypatch.setattr(capability_registry, "is_enabled", enabled)
    assert client.get("/pdf/files/f_1/download?exp=1&sig=signed").status_code == 503
    download.assert_not_called()


def test_unexpected_error_does_not_disclose_paths(setup):
    client, download = setup
    download.side_effect = OSError("private storage key")
    response = client.get("/pdf/files/f_1/download?exp=1&sig=signed")
    assert response.status_code == 503
    assert response.json() == {"error": "PDF capability is unavailable"}
