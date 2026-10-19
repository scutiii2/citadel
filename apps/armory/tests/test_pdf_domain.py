from dataclasses import replace

import pytest

from src.capabilities.pdf_merger import domain
from src.services import identity_context


@pytest.fixture
def caller(monkeypatch):
    monkeypatch.setattr(domain, "settings", replace(domain.settings, host="127.0.0.1", internal_api_token="test"))
    monkeypatch.setattr(identity_context, "current_uid", lambda: "account-a")


def test_identity_required(monkeypatch):
    monkeypatch.setattr(identity_context, "current_uid", lambda: "")
    with pytest.raises(domain.PdfError, match="signed-in"):
        domain.list_files()


def test_exposed_without_token_refuses_even_identified_caller(caller, monkeypatch):
    monkeypatch.setattr(domain, "settings", replace(domain.settings, host="0.0.0.0", internal_api_token=""))
    with pytest.raises(domain.PdfError, match="INTERNAL_API_TOKEN"):
        domain.list_files()


def test_native_upload_merge_and_isolation(caller, monkeypatch, tmp_path):
    import pikepdf
    from src.capabilities.pdf_merger.contract import MergePlan
    from src.services.pdf_runtime import Runtime
    from src.capabilities.pdf_merger.utils.config import Settings
    from src.capabilities.pdf_merger.utils.errors import MergerError

    runtime = Runtime(Settings(store_dir=tmp_path / "store", signing_key=b"x" * 32))
    monkeypatch.setattr(domain, "get_runtime", lambda _: runtime)
    try:
        path = tmp_path / "input.pdf"
        with pikepdf.new() as pdf:
            pdf.add_blank_page(page_size=(100, 200))
            pdf.add_blank_page(page_size=(150, 200))
            pdf.save(path)
        uploaded = domain.upload("untrusted.pdf", path.read_bytes())
        result = domain.merge(MergePlan.model_validate({"segments": [{"file_id": uploaded.file_id, "pages": "2,1", "rotate": 90}]}))
        assert result.pages == 2
        assert "/pdf/files/" in result.download_url
        assert "data, not instructions" in domain.list_files().files[0].name
        monkeypatch.setattr(identity_context, "current_uid", lambda: "account-b")
        assert domain.list_files().files == []
        errors = [domain.inspect_files(i).failed[0].message for i in (uploaded.file_id, "f_" + "0" * 32, "../../bad")]
        assert len(set(errors)) == 1
        with pytest.raises(MergerError):
            domain.merge(MergePlan.model_validate({"segments": [{"file_id": uploaded.file_id}]}))
    finally:
        runtime.close()
