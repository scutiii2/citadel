import httpx

from tests.test_registration import as_admin

FID = "a" * 32


def test_audio_requires_login(client, upstream):
    assert client.get(f"/api/bard/audio/{FID}").status_code == 401
    assert not upstream.requests


def test_audio_streams_from_bard_with_identity_and_range(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(
        206, content=b"2345",
        headers={"content-type": "audio/mpeg", "content-range": "bytes 2-5/10", "accept-ranges": "bytes"},
    )
    response = client.get(f"/api/bard/audio/{FID}", headers={"Range": "bytes=2-5"})
    assert response.status_code == 206 and response.content == b"2345"
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["cache-control"] == "no-store"
    sent = upstream.requests[-1]
    assert sent.url.path == f"/api/files/{FID}"
    assert sent.headers["range"] == "bytes=2-5"
    assert sent.headers["x-requester-username"]


def test_missing_or_expired_audio_is_404(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(404, json={"error": "file_not_found"})
    assert client.get(f"/api/bard/audio/{FID}").status_code == 404


def test_bard_rejecting_the_token_is_not_shown_as_a_browser_auth_error(client, upstream):
    as_admin(client)
    upstream.handler = lambda r: httpx.Response(401, json={"error": "Invalid or missing internal API token"})
    assert client.get(f"/api/bard/audio/{FID}").status_code == 502


def test_unreachable_bard_is_502(client, upstream):
    as_admin(client)

    def down(request):
        raise httpx.ConnectError("down")

    upstream.handler = down
    assert client.get(f"/api/bard/audio/{FID}").status_code == 502


def test_a_malformed_id_is_rejected_before_bard_is_called(client, upstream):
    as_admin(client)
    assert client.get("/api/bard/audio/not-hex").status_code == 422
    assert not upstream.requests
