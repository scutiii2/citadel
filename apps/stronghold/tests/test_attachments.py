"""/attachments: text is read here; PDFs and tables go to Armory, audio to Scribe, documents to Reader."""

from __future__ import annotations

from tests.auth_helpers import identity, caller, requester

import base64
import io

import httpx
from tests.conftest import TOOL_TOKEN
import pytest
from docx import Document
from fastapi.testclient import TestClient
from openpyxl import Workbook

from src.attachments.extraction import MAX_TEXT_CHARS

ANONYMOUS = identity(uid="")
PDF = {"file_id": "f_scan", "pages": 2, "kind": "pdf", "expires_at": 2000000000}
TABLE = {"table_id": "tbl-1", "filename": "sales.csv", "rows": 2, "columns": ["region", "units"], "sheet": None, "notes": []}


def body(name: str = "a.mp3", data: bytes = b"abc") -> dict:
    return {"filename": name, "data": base64.b64encode(data).decode()}


def post(client: TestClient, path: str, name: str, data: bytes = b"abc", **kwargs):
    return client.post(f"/attachments/{path}", json=body(name, data), **kwargs)


def down(_request):
    raise httpx.ConnectError("down")


def logged(platform) -> dict[str, str]:
    return {action: message for _uid, action, message in platform.actions}


# --- access ---------------------------------------------------------------------------------


@pytest.mark.parametrize("path, name", [("text", "a.txt"), ("table", "a.csv"), ("pdf", "a.pdf"), ("audio", "a.mp3"),
                                        ("document", "a.pdf"), ("dictate", "a.webm"), ("dictate/partial", "a.webm")])
def test_every_route_needs_the_requester(client: TestClient, armory, tools, path: str, name: str) -> None:
    assert post(client, path, name, headers=ANONYMOUS).status_code == 400
    assert not armory.requests and not any(t.requests for t in tools.values())


# --- text -----------------------------------------------------------------------------------


def test_text_and_code_files(client: TestClient) -> None:
    response = post(client, "text", "C:\\Users\\me\\notes.md", "# Title\n\nSome text ✓\n".encode())
    assert response.status_code == 200, response.text
    assert response.json() == {"filename": "notes.md", "text": "# Title\n\nSome text ✓", "char_count": 20, "truncated": False}

    long = post(client, "text", "big.log", b"x" * (MAX_TEXT_CHARS + 50)).json()
    assert (long["char_count"], long["truncated"]) == (MAX_TEXT_CHARS, True)


def test_office_files(client: TestClient) -> None:
    document = Document()
    document.add_paragraph("Quarterly report")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Revenue", "42"
    buffer = io.BytesIO()
    document.save(buffer)
    assert post(client, "text", "report.docx", buffer.getvalue()).json()["text"] == "Quarterly report\nRevenue | 42"

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Activity", None, "Action"])
    sheet.append(["deploy", "api", None])
    buffer = io.BytesIO()
    workbook.save(buffer)
    assert post(client, "text", "plan.xlsx", buffer.getvalue()).json()["text"] == "Activity |  | Action\ndeploy | api"


def test_unreadable_files_are_refused_with_a_reason(client: TestClient) -> None:
    cases = {
        ("movie.mp4", b"\x00\x01"): "Can't read '.mp4' files",
        ("empty.txt", b""): None,  # refused by the model (min_length) before reading
        ("blank.txt", b"   \n "): "No readable text found in this file.",
        ("binary.txt", bytes(range(128, 256)) * 10): "This doesn't look like a text file",
        ("broken.pdf", b"%PDF-1.4 garbage"): "Could not read this PDF",
    }
    for (filename, content), message in cases.items():
        response = post(client, "text", filename, content)
        if message is None:
            assert response.status_code == 422
            continue
        assert response.status_code == 400, (filename, response.text)
        assert response.json()["detail"].startswith(message), response.json()

    bad = client.post("/attachments/text", json={"filename": "a.txt", "data": "not base64!"})
    assert (bad.status_code, bad.json()["detail"]) == (400, "data must be base64")


# --- table (Armory) -------------------------------------------------------------------------


def armory_table(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/upload/table" and request.method == "POST":
        if b'filename="bad.csv"' in request.content:
            return httpx.Response(400, json={"error": "The file needs a header row and at least one data row."})
        return httpx.Response(200, json=TABLE)
    return httpx.Response(404, json={"error": "no route"})


def test_a_csv_is_forwarded_and_the_table_info_comes_back(client: TestClient, armory, platform) -> None:
    armory.handler = armory_table

    response = post(client, "table", "C:\\Users\\me\\sales.csv", b"region,units\nEU,1\n")

    assert response.status_code == 200, response.text
    assert response.json() == TABLE
    sent = armory.requests[-1]
    assert sent.url.path == "/upload/table"
    assert b'filename="sales.csv"' in sent.content and b"region,units" in sent.content
    assert requester(sent)["username"] == "ana" and requester(sent)["sub"] == "u-1"
    assert caller(sent, "armory") == "stronghold"
    assert sent.extensions["timeout"]["read"] == 120.0  # a big workbook can take a while to parse
    assert logged(platform)["attachments.table"] == "Attached 'sales.csv' (18 bytes) as a table"


def test_other_table_types_and_bad_input_are_refused_before_armory(client: TestClient, armory) -> None:
    refused = post(client, "table", "notes.txt")
    assert refused.status_code == 400 and ".csv and .xlsx" in refused.json()["detail"]
    assert client.post("/attachments/table", json={"filename": "a.csv", "data": "not base64!"}).status_code == 400
    assert armory.requests == []


def test_armory_refusing_a_table_is_a_400_with_its_reason(client: TestClient, armory) -> None:
    armory.handler = armory_table

    response = post(client, "table", "bad.csv")

    assert response.status_code == 400 and "header row" in response.json()["detail"]


def test_an_unreachable_armory_is_a_502(client: TestClient, armory) -> None:
    armory.handler = down

    assert post(client, "table", "sales.csv").status_code == 502


def test_a_token_mismatch_at_armory_is_a_502_not_a_400(client: TestClient, armory) -> None:
    armory.handler = lambda request: httpx.Response(401, json={"error": "bad internal token"})

    response = post(client, "table", "sales.csv")

    assert response.status_code == 502 and response.json()["detail"] == "armory is unreachable"


def test_a_table_answer_without_an_id_is_a_502(client: TestClient, armory) -> None:
    armory.handler = lambda request: httpx.Response(200, json={"rows": 1})

    assert post(client, "table", "sales.csv").status_code == 502


def test_a_table_over_15_mb_is_refused_before_armory(client: TestClient, armory) -> None:
    # The base64 length cap in the model catches it first.
    assert post(client, "table", "big.csv", b"x" * (15 * 1024 * 1024 + 1)).status_code == 422
    assert armory.requests == []


# --- pdf (Armory) ---------------------------------------------------------------------------


def test_the_original_is_uploaded_without_needing_extractable_text(client: TestClient, armory, platform) -> None:
    armory.handler = lambda request: httpx.Response(200, json=PDF)

    response = post(client, "pdf", "C:\\docs\\scan.pdf", b"%PDF-scan")

    assert response.status_code == 200, response.text
    assert response.json()["file_id"] == "f_scan"
    assert response.json()["filename"] == "scan.pdf" and response.json()["text"] == ""
    sent = armory.requests[-1]
    assert sent.url.path == "/upload/pdf" and requester(sent)["username"] == "ana"
    assert b"%PDF-scan" in sent.content and b'filename="scan.pdf"' in sent.content
    assert sent.extensions["timeout"]["read"] == 120
    assert "attachments.pdf" in logged(platform)


def test_an_image_is_stored_without_text_extraction(client: TestClient, armory) -> None:
    armory.handler = lambda request: httpx.Response(200, json={**PDF, "kind": "image"})

    response = post(client, "pdf", "image.png", b"image")

    assert response.status_code == 200 and response.json()["kind"] == "image"


def test_pdf_input_errors_never_reach_armory(client: TestClient, armory) -> None:
    assert post(client, "pdf", "file.exe").status_code == 400
    assert client.post("/attachments/pdf", json={"filename": "a.pdf", "data": "??"}).status_code == 400
    assert armory.requests == []


def test_unavailable_or_invalid_pdf_metadata_is_a_502(client: TestClient, armory) -> None:
    armory.handler = lambda request: httpx.Response(200, json={"file_id": "f_1"})
    assert post(client, "pdf", "a.pdf").status_code == 502
    armory.handler = down
    assert post(client, "pdf", "a.pdf").status_code == 502


def test_a_pdf_refusal_is_visible(client: TestClient, armory) -> None:
    armory.handler = lambda request: httpx.Response(400, json={"error": "Encrypted PDF"})

    response = post(client, "pdf", "a.pdf")

    assert response.status_code == 400 and "Encrypted PDF" in response.json()["detail"]


def test_a_successful_pdf_upload_keeps_its_optional_preview(client: TestClient, armory, monkeypatch) -> None:
    from types import SimpleNamespace

    from src.attachments import routes

    async def extract(filename, content):
        return SimpleNamespace(text="PDF text preview", char_count=16, truncated=True)

    monkeypatch.setattr(routes, "extract_text_async", extract)
    armory.handler = lambda request: httpx.Response(200, json=PDF)

    result = post(client, "pdf", "a.pdf").json()

    assert result["text"] == "PDF text preview" and result["truncated"] is True
    assert result["file_id"] == "f_scan"


# --- audio (Scribe) -------------------------------------------------------------------------


def test_audio_is_forwarded_to_scribe_with_identity(client: TestClient, tools, platform) -> None:
    tools["scribe"].handler = lambda r: httpx.Response(
        200, json={"file_id": "a" * 32, "duration_s": 3.2, "size_bytes": 3, "expires_at": 99.0})

    response = post(client, "audio", "..\\x\\talk.m4a", b"abc")

    assert response.status_code == 200
    assert response.json() == {"filename": "talk.m4a", "file_id": "a" * 32, "duration_s": 3.2, "expires_at": 99.0}
    sent = tools["scribe"].requests[-1]
    assert sent.url.host == "scribe.test" and sent.url.path == "/api/files" and sent.content == b"abc"
    assert sent.headers["x-requester-username"] == "ana" and sent.headers["x-filename"] == "talk.m4a"
    assert sent.headers["x-internal-token"] == TOOL_TOKEN and TOOL_TOKEN not in response.text
    assert "attachments.audio" in logged(platform)


@pytest.mark.parametrize("path", ["audio", "dictate", "dictate/partial"])
def test_audio_that_cannot_be_right_never_reaches_scribe(client: TestClient, tools, path: str) -> None:
    assert post(client, path, "a.exe").status_code == 400
    assert client.post(f"/attachments/{path}", json={"filename": "a.mp3", "data": "!!!"}).status_code == 400
    assert post(client, path, "a.webm", b"x" * (20 * 1024 * 1024 + 1)).status_code == 413
    assert not tools["scribe"].requests


def test_scribe_rejecting_audio_is_a_400_with_its_message(client: TestClient, tools) -> None:
    tools["scribe"].handler = lambda r: httpx.Response(400, json={"message": "Not audio."})

    response = post(client, "audio", "a.mp3")

    assert response.status_code == 400 and "Not audio." in response.text


@pytest.mark.parametrize("code, expected", [(400, 400), (413, 413), (401, 502), (503, 502), (422, 502)])
def test_scribe_errors_map_to_statuses(client: TestClient, tools, code: int, expected: int) -> None:
    tools["scribe"].handler = lambda r: httpx.Response(code, json={"message": "Failed"})
    response = post(client, "dictate", "a.webm")
    assert response.status_code == expected
    if code == 401:
        assert response.json()["detail"] == "Scribe refused the token. Check Stronghold Admin."

    tools["scribe"].handler = down
    assert post(client, "audio", "a.mp3").status_code == 502


def test_dictation_returns_the_transcript_and_logs_no_words(client: TestClient, tools, platform) -> None:
    tools["scribe"].handler = lambda r: httpx.Response(200, json={"text": "hello", "duration_s": 2.5})

    response = post(client, "dictate", "../speech.webm")

    assert response.status_code == 200 and response.json() == {"text": "hello", "duration_s": 2.5}
    sent = tools["scribe"].requests[-1]
    assert sent.url.path == "/api/transcribe" and sent.content == b"abc" and sent.headers["x-filename"] == "speech.webm"
    assert logged(platform)["attachments.dictate"] == "Transcribed 3 bytes of dictated audio"


def test_a_partial_dictation_leaves_no_log_line(client: TestClient, tools, platform) -> None:
    tools["scribe"].handler = lambda r: httpx.Response(200, json={"text": "hel", "duration_s": 1.0})

    response = post(client, "dictate/partial", "a.webm")

    assert response.json() == {"text": "hel", "duration_s": 1.0}
    assert tools["scribe"].requests[-1].url.path == "/api/transcribe-partial"
    assert platform.actions == []


# --- document (Reader) ----------------------------------------------------------------------


def test_a_document_is_forwarded_to_reader_with_identity(client: TestClient, tools, platform) -> None:
    tools["reader"].handler = lambda r: httpx.Response(
        200, json={"file_id": "b" * 32, "page_count": 2, "size_bytes": 4, "expires_at": 99.0})

    response = post(client, "document", "..\\x\\scan.pdf", b"%PDF")

    assert response.status_code == 200
    assert response.json() == {"filename": "scan.pdf", "file_id": "b" * 32, "page_count": 2, "expires_at": 99.0}
    sent = tools["reader"].requests[-1]
    assert sent.url.host == "reader.test" and sent.url.path == "/api/files" and sent.content == b"%PDF" and sent.headers["x-filename"] == "scan.pdf"
    assert sent.headers["x-requester-username"] == "ana" and sent.headers["x-internal-token"] == TOOL_TOKEN
    assert TOOL_TOKEN not in response.text and "attachments.document" in logged(platform)


def test_a_document_that_cannot_be_right_never_reaches_reader(client: TestClient, tools) -> None:
    assert post(client, "document", "a.exe").status_code == 400
    assert post(client, "document", "a.pdf", b"x" * (20 * 1024 * 1024 + 1)).status_code == 413
    assert not tools["reader"].requests


def test_reader_rejection_is_a_400_and_outage_is_a_502(client: TestClient, tools) -> None:
    tools["reader"].handler = lambda r: httpx.Response(400, json={"message": "Not a document."})
    response = post(client, "document", "a.pdf")
    assert response.status_code == 400 and "Not a document." in response.text

    tools["reader"].handler = lambda r: httpx.Response(401, json={"error": "Invalid or missing token"})
    refused = post(client, "document", "a.pdf")
    assert refused.status_code == 502
    assert refused.json()["detail"] == "Reader refused the token. Check Stronghold Admin."
