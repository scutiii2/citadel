"""Native HTTP uploads, identity propagation, merging and signed attachments."""
import asyncio
import importlib
from dataclasses import replace
from io import BytesIO
from urllib.parse import urlsplit, parse_qs

import pikepdf
from PIL import Image
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from src import command_routes, upload_routes
from src.services import capability_registry
from src.services.identity_context import IdentityContextMiddleware
from src.capabilities.pdf_merger.utils.pdf_runtime import Runtime

HEADERS = {"X-Internal-Token": "shared", "X-Requester-UID": "account-alice", "X-Requester-Username": "same-name"}
OTHER = {**HEADERS, "X-Requester-UID": "account-bob"}

@pytest.fixture
def native_client(monkeypatch, tmp_path):
    # Capability-loader tests may unload/reimport these modules. Patch the
    # same current module that the production routes import lazily.
    domain = importlib.import_module("src.capabilities.pdf_merger.domain")
    MergePlan = importlib.import_module("src.capabilities.pdf_merger.contract").MergePlan
    Settings = importlib.import_module("src.capabilities.pdf_merger.utils.config").Settings
    MergerError = importlib.import_module("src.capabilities.pdf_merger.utils.errors").MergerError
    test_settings = replace(domain.settings, host="127.0.0.1", internal_api_token="shared")
    monkeypatch.setattr(domain, "settings", test_settings)
    monkeypatch.setattr(upload_routes, "settings", test_settings)
    monkeypatch.setattr(capability_registry, "is_enabled", lambda _: True)
    runtime = Runtime(Settings(store_dir=tmp_path / "store", signing_key=b"x" * 32, public_base_url="http://testserver"))
    monkeypatch.setattr(domain, "get_runtime", lambda _: runtime)

    # A test-only adapter calls the same domain seam as MCP, inside the
    # request context, to exercise ownership across real HTTP uploads.
    async def exercise(request):
        body = await request.json()
        if body["operation"] == "list":
            result = await asyncio.to_thread(domain.list_files)
        elif body["operation"] == "inspect":
            result = await asyncio.to_thread(domain.inspect_files, body["file_ids"])
        else:
            try:
                result = await asyncio.to_thread(domain.merge, MergePlan.model_validate(body["plan"]))
            except MergerError:
                return JSONResponse({"error": "File is not available"}, status_code=400)
        return JSONResponse(result.model_dump(mode="json"))

    app = Starlette()
    app.add_middleware(IdentityContextMiddleware)
    upload_routes.install_upload_routes(app)
    command_routes.install_command_routes(app)
    app.add_route("/test-domain", exercise, methods=["POST"])
    try:
        with TestClient(app) as client:
            yield client
    finally:
        runtime.close()


def pdf_bytes(widths):
    stream = BytesIO()
    with pikepdf.new() as pdf:
        for width in widths:
            pdf.add_blank_page(page_size=(width, 300))
        pdf.save(stream)
    return stream.getvalue()


def test_original_pdf_and_image_uploads_merge_and_download(native_client):
    client = native_client
    image = BytesIO()
    Image.new("RGB", (10, 10), "red").save(image, format="PNG")
    originals = [("first.pdf", pdf_bytes([100, 101])), ("second.pdf", pdf_bytes([200])), ("photo.png", image.getvalue())]
    uploads = []
    for name, content in originals:
        response = client.post("/upload/pdf", headers=HEADERS, files={"file": (name, content)})
        assert response.status_code == 200, response.text
        assert response.json()["name"] == name
        uploads.append(response.json())
    inspected = client.post("/test-domain", headers=HEADERS, json={"operation": "inspect", "file_ids": ",".join(f["file_id"] for f in uploads)}).json()
    assert [f["pages"] for f in inspected["files"]] == [2, 1, 1]
    original_url = inspected["files"][0]["download_url"]
    assert client.get(original_url).content == originals[0][1]
    plan = {"segments": [{"file_id": uploads[0]["file_id"], "pages": "2,1", "rotate": 90}, {"file_id": uploads[1]["file_id"]}, {"file_id": uploads[2]["file_id"]}]}
    result = client.post("/test-domain", headers=HEADERS, json={"operation": "merge", "plan": plan})
    assert result.status_code == 200, result.text
    assert result.json()["pages"] == 4
    downloaded = client.get(result.json()["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["cache-control"] == "no-store"
    with pikepdf.open(BytesIO(downloaded.content)) as pdf:
        assert [round(float(p.mediabox[2])) for p in list(pdf.pages)[:3]] == [101, 100, 200]
        assert [int(p.obj.get("/Rotate", 0)) for p in list(pdf.pages)[:2]] == [90, 90]


def test_same_username_different_uids_are_isolated_and_signed_links_expire(native_client):
    client = native_client
    uploaded = client.post("/upload/pdf", headers=HEADERS, files={"file": ("scan.pdf", pdf_bytes([100]))}).json()
    assert client.post("/test-domain", headers=OTHER, json={"operation": "list"}).json()["files"] == []
    inspected = client.post("/test-domain", headers=OTHER, json={"operation": "inspect", "file_ids": uploaded["file_id"]}).json()
    assert inspected["files"] == [] and len(inspected["failed"]) == 1
    plan = {"segments": [{"file_id": uploaded["file_id"]}]}
    assert client.post("/test-domain", headers=OTHER, json={"operation": "merge", "plan": plan}).status_code == 400
    own = client.post("/test-domain", headers=HEADERS, json={"operation": "inspect", "file_ids": uploaded["file_id"]}).json()
    url = own["files"][0]["download_url"]
    parts = urlsplit(url)
    signature = parse_qs(parts.query)["sig"][0]
    assert client.get(url).status_code == 200
    for query in ("?exp=0&sig=" + signature, "?exp=2000000000&sig=forged"):
        response = client.get(parts.path + query)
        assert response.status_code == 404
        assert response.json() == {"error": "File is not available"}
