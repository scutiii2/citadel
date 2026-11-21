import pytest

from tests.test_registration import as_admin


@pytest.mark.parametrize("method, url", [
    ("GET", "/api/notes"), ("POST", "/api/notes"), ("GET", "/api/notes/tags"), ("POST", "/api/notes/suggest-tags"),
    ("POST", "/api/notes/generate-tag"), ("GET", "/api/notes/" + "a" * 32), ("DELETE", "/api/notes/" + "a" * 32),
    ("GET", "/api/memory"), ("POST", "/api/memory"), ("PUT", "/api/memory/1"), ("DELETE", "/api/memory/1"),
])
def test_the_old_routes_are_gone_and_nothing_is_forwarded(client, upstream, method, url):
    as_admin(client)
    upstream.requests.clear()
    answer = client.request(method, url, json={})
    assert answer.status_code in (404, 405)
    assert not upstream.requests
