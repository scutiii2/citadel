import base64

import httpx

from tests.test_registration import as_admin


def body(name="scan.pdf", data=b"%PDF"):
    return {"filename": name, "data": base64.b64encode(data).decode()}


def test_document_requires_login(client, upstream):
    assert client.post("/api/attachments/document", json=body()).status_code == 401
    assert not upstream.requests


def test_document_is_forwarded_to_reader_with_identity(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(
        200, json={"file_id": "b" * 32, "page_count": 2, "size_bytes": 4, "expires_at": 99.0}
    )
    response = client.post("/api/attachments/document", json=body("..\\x\\scan.pdf"))
    assert response.status_code == 200
    assert response.json() == {"filename": "scan.pdf", "file_id": "b" * 32, "page_count": 2, "expires_at": 99.0}
    sent = upstream.requests[-1]
    assert sent.url.path == "/api/files" and sent.content == b"%PDF"
    assert sent.headers["x-filename"] == "scan.pdf"


def test_unsupported_suffix_is_400_without_calling_reader(client, upstream):
    as_admin(client)
    assert client.post("/api/attachments/document", json=body("a.exe")).status_code == 400
    assert not upstream.requests


def test_reader_rejection_is_400_and_outage_is_502(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(422, json={"message": "Not a document."})
    response = client.post("/api/attachments/document", json=body())
    assert response.status_code == 400 and "Not a document." in response.text
    upstream.handler = lambda r: httpx.Response(401, json={"error": "Invalid or missing token"})
    assert client.post("/api/attachments/document", json=body()).status_code == 502
