"""Status, admin and audio routes of the tool services, through the app with the shared fixtures."""

import httpx
import pytest
from src.tool_services.outside import OutsideError

from src.tool_services.store import ToolStore


def seed(app_state, name="bard", token="parent"):
    ToolStore(app_state.settings.data_dir / "settings.db").put(
        name, {"enabled": True, "service_id": "s", "token": token, "origins": [{"origin_id": "o1"}]})


def test_status_lists_the_three_services_with_reasons(client):
    store = ToolStore(client.app.state.settings.data_dir / "settings.db")
    for name in ("bard", "scribe", "reader"):
        store.clear(name)
    response = client.get("/tool-services/status")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"bard", "scribe", "reader"}
    assert body["bard"] == {"ready": False, "reason": "Configure Bard in Stronghold Admin."}


def test_the_admin_routes_refuse_every_caller_but_portcullis(as_service):
    legion = as_service("legion")
    for method, path in (
        ("GET", "/admin/tool-services"), ("POST", "/admin/tool-services/lookup"),
        ("PUT", "/admin/tool-services/bard"), ("DELETE", "/admin/tool-services/bard"),
        ("POST", "/admin/tool-services/bard/test"),
    ):
        assert legion.request(method, path).status_code == 403


def test_the_admin_view_never_shows_a_token(client, as_service):
    seed(client.app.state)
    shown = as_service("portcullis").get("/admin/tool-services")
    assert shown.status_code == 200 and "parent" not in shown.text
    bard = next(s for s in shown.json()["services"] if s["name"] == "bard")
    assert bard["has_token"] is True and bard["ready"] is True


def test_saving_by_address_registers_origins_and_keeps_an_unretyped_token(client, as_service, monkeypatch):
    ToolStore(client.app.state.settings.data_dir / "settings.db").clear("bard")
    registered = {}

    async def entry(addresses, previous):
        registered["addresses"], registered["previous"] = addresses, previous
        return {"service_id": "s-bard", "origins": [{"origin_id": "o1"}]}

    monkeypatch.setattr(client.app.state.outside, "entry_from_addresses", entry)
    admin = as_service("portcullis")
    first = admin.put("/admin/tool-services/bard", json={"token": "parent", "addresses": [{"address": "http://bard:29400", "name": "bard"}]})
    assert first.status_code == 200 and first.json()["has_token"] is True
    assert registered["addresses"] == [{"address": "http://bard:29400", "name": "bard"}]
    assert registered["previous"]["origins"] == []
    assert first.json()["origins"] == [{"origin_id": "o1", "origin": "http://bard.test", "has_override": False}]
    again = admin.put("/admin/tool-services/bard", json={"enabled": False})
    assert again.json()["enabled"] is False and again.json()["has_token"] is True   # the token was kept
    assert ToolStore(client.app.state.settings.data_dir / "settings.db").get("bard")["token"] == "parent"


def test_a_treasury_refusal_saves_nothing(client, as_service, monkeypatch):
    ToolStore(client.app.state.settings.data_dir / "settings.db").clear("bard")

    async def refuse(addresses, previous):
        raise OutsideError("[1002] Treasury is unavailable. Nothing was saved.", 502)

    monkeypatch.setattr(client.app.state.outside, "entry_from_addresses", refuse)
    response = as_service("portcullis").put("/admin/tool-services/bard", json={"addresses": [{"address": "http://x:1", "name": "x"}]})
    assert response.status_code == 502 and response.json()["detail"].startswith("[1002]")
    assert ToolStore(client.app.state.settings.data_dir / "settings.db").get("bard")["origins"] == []


def test_a_slow_catalog_operation_cannot_save_after_the_deadline(client, as_service, monkeypatch):
    import asyncio
    from src.tool_services import routes

    store = ToolStore(client.app.state.settings.data_dir / "settings.db")
    store.clear("bard")
    monkeypatch.setattr(routes, "ADMIN_SAVE_SECONDS", 0.01, raising=False)

    async def slower_than_the_save_budget(addresses, previous):
        await asyncio.sleep(0.04)
        return {"service_id": "s", "origins": [{"origin_id": "o1"}]}

    monkeypatch.setattr(client.app.state.outside, "entry_from_addresses", slower_than_the_save_budget)
    response = as_service("portcullis").put(
        "/admin/tool-services/bard", json={"addresses": [{"address": "http://bard:29400"}]})
    assert response.status_code == 502
    assert response.json()["detail"] == "[1002] Treasury is unavailable. Nothing was saved."
    assert store.get("bard")["origins"] == []


def test_the_last_origin_leaving_the_catalog_clears_readiness(client, as_service):
    store = ToolStore(client.app.state.settings.data_dir / "settings.db")
    store.put("bard", {"enabled": True, "service_id": "s", "token": "parent",
                       "origins": [{"origin_id": "deleted"}]})
    expected = {"ready": False, "reason": "Configure Bard in Stronghold Admin."}
    assert client.get("/tool-services/status").json()["bard"] == expected
    card = next(item for item in as_service("portcullis").get("/admin/tool-services").json()["services"]
                if item["name"] == "bard")
    assert {key: card[key] for key in expected} == expected
    assert card["origins"] == [{"origin_id": "deleted", "origin": None, "has_override": False}]


def test_invalid_admin_body_does_not_echo_the_token(as_service):
    admin = as_service("portcullis")
    response = admin.put("/admin/tool-services/bard", json=[{"token": "malformed-draft-token"}])
    assert response.status_code == 422
    assert "malformed-draft-token" not in response.text


def test_an_unknown_service_name_is_a_404(client, as_service):
    assert as_service("portcullis").put("/admin/tool-services/lens", json={"enabled": True}).status_code == 404

def test_audio_streams_with_range_and_maps_errors(client, tools):
    file_id = "a" * 32

    def upstream(request):
        if request.url.path == "/api/speak":
            return httpx.Response(200, json={"file_id": file_id, "duration_s": 1.0, "voice": "default"})
        assert request.url.path == f"/api/files/{file_id}"
        assert request.headers["range"] == "bytes=0-3"
        return httpx.Response(206, content=b"abcd", headers={
            "content-range": "bytes 0-3/10", "accept-ranges": "bytes",
        })

    tools["bard"].handler = upstream
    assert client.post("/bard/speak", json={"text": "hello"}).status_code == 200
    path = f"/speech/audio/{file_id}"
    response = client.get(path, headers={"Range": "bytes=0-3"})
    assert response.status_code == 206 and response.content == b"abcd"
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["content-length"] == "4"
    assert response.headers["content-range"] == "bytes 0-3/10"
    assert response.headers["accept-ranges"] == "bytes"
    for status in (404, 416):
        tools["bard"].handler = lambda _, status=status: httpx.Response(status)
        assert client.get(path).status_code == status

    tools["bard"].handler = lambda _: httpx.Response(200, headers={"content-length": str(64 * 1024 * 1024 + 1)})
    assert client.get(path).status_code == 502


def test_audio_without_a_length_closes_the_upstream_at_the_stream_limit(client, tools, monkeypatch):
    from src.tool_services import routes

    class Audio(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"x" * 65_536
            yield b"x" * 65_536

        async def aclose(self):
            self.closed = True

    monkeypatch.setattr(routes, "MAX_AUDIO", 65_537)
    file_id = "a" * 32
    stream = Audio()
    tools["bard"].handler = lambda _: httpx.Response(
        200, json={"file_id": file_id, "duration_s": 1.0, "voice": "default"})
    assert client.post("/bard/speak", json={"text": "hello"}).status_code == 200
    tools["bard"].handler = lambda _: httpx.Response(200, stream=stream)
    with pytest.raises(RuntimeError, match="Bard audio exceeded the stream limit"):
        client.get(f"/speech/audio/{file_id}")
    assert stream.closed


def test_tool_origins_on_different_ports_never_share_cookies(client, tools, monkeypatch):
    store = ToolStore(client.app.state.settings.data_dir / "settings.db")
    store.put("bard", {"enabled": True, "service_id": "s", "token": "parent",
                       "origins": [{"origin_id": "main"}, {"origin_id": "backup", "header_value": "second"}]})
    resolve = {"main": "http://bard.test:29400", "backup": "http://bard.test:29401"}.__getitem__
    monkeypatch.setattr(client.app.state.connections, "_resolve", resolve)
    first = True

    def upstream(request):
        nonlocal first
        if first:
            first = False
            return httpx.Response(200, json={"voices": ["default"]}, headers={
                "set-cookie": "reflected=parent; Path=/",
            })
        if request.url.port == 29400:
            raise httpx.ConnectError("down")
        assert request.headers["x-internal-token"] == "second"
        assert "cookie" not in request.headers
        return httpx.Response(200, json={"voices": ["backup"]})

    tools["bard"].handler = upstream
    assert client.get("/bard/voices").json() == {"voices": ["default"]}
    assert client.get("/bard/voices").json() == {"voices": ["backup"]}


def test_the_admin_lookup_and_clear_do_not_return_tokens(client, as_service, monkeypatch):
    seed(client.app.state)

    async def lookup(address):
        return {"found": True, "origin": address, "path": "", "origin_id": "o1", "group": {"name": "bard"}}

    monkeypatch.setattr(client.app.state.outside, "lookup", lookup)
    admin = as_service("portcullis")
    response = admin.post("/admin/tool-services/lookup", json={"address": "http://bard:29400"})
    assert response.status_code == 200 and response.json()["found"] is True
    removed = admin.delete("/admin/tool-services/bard")
    assert removed.status_code == 200
    assert removed.json()["has_token"] is False and removed.json()["origins"] == []
    assert "parent" not in removed.text


def test_the_admin_probes_the_saved_origin_without_returning_the_token(client, tools, as_service):
    seed(client.app.state)
    seen = []

    def upstream(request):
        assert request.headers["x-internal-token"] == "parent"
        seen.append(request.url.path)
        status = 401 if len(seen) == 4 else 200
        return httpx.Response(status, json={"voices": ["parent"]})

    tools["bard"].handler = upstream
    admin = as_service("portcullis")
    good = admin.post("/admin/tool-services/bard/test")
    assert good.status_code == 200 and "parent" not in good.text
    assert good.json()["origins"] == [{"origin_id": "o1", "ok": True, "message": "Ready."}]

    refused = admin.post("/admin/tool-services/bard/test")
    assert refused.status_code == 200 and "parent" not in refused.text
    assert refused.json()["origins"] == [{"origin_id": "o1", "ok": False, "code": "401", "message": "The token was refused."}]
    assert refused.json()["code"] == "401"
    assert seen == ["/health", "/api/voices", "/health", "/api/voices"]
