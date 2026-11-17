"""GET /api/attachments/files/{id}/content: an owned chat attachment, streamed from Armory."""
from tests.auth_helpers import requester
import httpx

from tests.test_registration import as_admin


def test_chat_image_content_uses_owned_stream_without_capability_subscription(client, upstream):
    url = "/api/attachments/files/f_photo/content"
    assert client.get(url).status_code == 401
    as_admin(client)
    upstream.handler = lambda request: httpx.Response(200, content=b"image", headers={"content-type": "image/png"})
    response = client.get(url, headers={"X-Requester-Uid": "foreign"})
    assert response.status_code == 200, response.text
    assert response.content == b"image"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    assert upstream.requests[-1].url.path == "/pdf/ui/files/f_photo/content"
    assert requester(upstream.requests[-1])["username"] == "root"
    assert requester(upstream.requests[-1])["sub"] != "foreign"
    upstream.handler = lambda request: httpx.Response(404, json={"error": {"code": "file_not_found", "message": "Unavailable"}})
    assert client.get(url).status_code == 404


def test_chat_image_content_requires_download_permission(client, email, upstream):
    from tests.test_permission_split import limited_account
    limited_account(client, email, "files.upload")
    assert client.get("/api/attachments/files/f_photo/content").status_code == 403
    assert not upstream.requests
