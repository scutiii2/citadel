"""Speech proxies must refuse each missing permission before touching upstream."""
import pytest

from tests.test_admin import login, make_member, role_by_name
from tests.test_registration import as_admin


@pytest.mark.parametrize("missing", ["files.upload", "tools.execute", "files.download"])
def test_speech_requires_each_permission(client, email, upstream, missing):
    make_member(client, email)
    as_admin(client)
    role = role_by_name(client, "Member")["id"]
    for permission in ["files.upload", "tools.execute", "files.download"]:
        assert client.put(f"/api/admin/roles/{role}/permissions/{permission}").status_code == 200
    assert client.delete(f"/api/admin/roles/{role}/permissions/{missing}").status_code == 200
    client.post("/api/auth/logout", json={})
    login(client, "alice")
    upstream.requests.clear()
    if missing == "files.upload":
        assert client.post("/api/attachments/dictate", json={"filename": "dictation.webm", "data": "YWJj"}).status_code == 403
    else:
        assert client.get("/api/bard/voices").status_code == 403
        assert client.post("/api/bard/speak", json={"text": "hi", "voice": "v1"}).status_code == 403
    assert not upstream.requests
