import asyncio

import anyio
import httpx
from mcp import types
from starlette.applications import Starlette
from starlette.testclient import TestClient

from src.services.service_auth import install_auth
from tests.auth_helpers import FreshHeaders


def test_admin_records_keep_credentials_write_only_and_test_rest(tmp_path):
    from src.connection_admin import install_connection_admin
    from src.services.connections import ConnectionStore

    def health(request):
        assert request.headers["X-Internal-Token"] == "tool-test-value"
        if request.url.path == "/api/voices":
            assert request.headers["X-Requester-Username"] == "ada"
            return httpx.Response(200, json={"voices": []})
        assert request.url.path == "/health"
        return httpx.Response(200, json={"ok": True, "ready": True})

    app = Starlette()
    install_auth(app)
    install_connection_admin(app, ConnectionStore(tmp_path / "settings.db"),
                             httpx.AsyncClient(transport=httpx.MockTransport(health)))
    path = "/admin/connections"
    with TestClient(app) as client:
        assert client.get(path, headers=FreshHeaders(caller="stronghold")).status_code == 403
        before = client.get(path, headers=FreshHeaders())
        assert [item["name"] for item in before.json()] == ["bard", "scribe", "reader"]
        updated = client.patch(f"{path}/bard", headers=FreshHeaders(), json={
            "rest": {"base_url": "http://bard", "auth": {"kind": "token", "token": "tool-test-value"}}
        })
        assert updated.status_code == 200
        assert updated.json()["rest"]["auth"] == {"kind": "token", "configured": True}
        assert "tool-test-value" not in updated.text
        listed = client.get(path, headers=FreshHeaders())
        assert "tool-test-value" not in listed.text
        checked = client.post(f"{path}/bard/test/rest", headers=FreshHeaders(uid="one", username="ada"))
        assert checked.json()["ok"] is True
        assert "tool-test-value" not in checked.text
        assert client.delete(f"{path}/bard", headers=FreshHeaders()).status_code == 400


def test_address_changes_cannot_reuse_a_secret_on_another_origin(tmp_path):
    from src.services.connections import ConnectionStore

    store = ConnectionStore(tmp_path / "settings.db")
    store.update("bard", {"rest": {"base_url": "https://bard", "auth": {"kind": "token", "token": "fixture"}}})
    changed = store.update("bard", {"rest": {"base_url": "https://different-host"}})
    assert store.view(changed)["rest"]["auth"] == {"kind": "token", "configured": False}
    assert store.view(changed)["ready"] is False


def test_editing_rest_keeps_the_migrated_mcp_url_and_secret(tmp_path, monkeypatch):
    from src.citadel_auth import settings_store
    from src.services.app_config import load_extension_config
    from src.services.connections import ConnectionStore

    path = tmp_path / "settings.db"
    monkeypatch.setenv("PLAN14_TEST_HOST", "bard.example")
    monkeypatch.setenv("PLAN14_TEST_TOKEN", "upstream-fixture")
    settings_store.put(path, "extensions", "bard", {
        "label": "Bard", "url": "http://${PLAN14_TEST_HOST}/mcp",
        "headers": {"X-Internal-Token": "${PLAN14_TEST_TOKEN}"},
    })
    ConnectionStore(path).update("bard", {
        "label": "Bard ${PLAN14_TEST_TOKEN}",
        "rest": {"base_url": "http://bard.example", "auth": {"kind": "token", "token": "rest-fixture"}},
        "mcp": {"auth": {"kind": "token"}},
    })
    restored = load_extension_config(path, "bard")
    assert restored.url == "http://bard.example/mcp"
    assert restored.headers["X-Internal-Token"] == "upstream-fixture"
    assert restored.label == "Bard ${PLAN14_TEST_TOKEN}"


def test_legacy_create_preserves_an_existing_rest_only_record(tmp_path):
    from src.services.connections import ConnectionStore

    store = ConnectionStore(tmp_path / "settings.db")
    store.update("lens", {"label": "Original", "enabled": False, "rest": {"base_url": "http://lens"}})
    name = store.save_legacy_mcp("lens", {"label": "Lens", "description": "", "url": "http://lens/mcp"}, create=True)
    assert name == "lens_2"
    assert store.get("lens")["label"] == "Original"
    assert store.get("lens")["mcp"] is None


async def test_internal_mcp_origin_is_checked_before_the_handshake(monkeypatch):
    from contextlib import AsyncExitStack

    from src.services import extensions
    from src.services.app_config import ExtensionConfig

    async def unexpected(_url):
        raise AssertionError("A request was attempted to an untrusted internal origin.")

    monkeypatch.setattr(extensions, "_check_tcp_reachable", unexpected)
    async with AsyncExitStack() as stack:
        try:
            await extensions.ExtensionRegistry._open_and_list(stack, ExtensionConfig(
                id="outside", label="Outside", description="", transport="http",
                url="https://outside.example/mcp", internal=True, audience="treasury"))
        except ValueError as error:
            assert "Treasury catalog" in str(error)
        else:
            raise AssertionError("Internal connection unexpectedly accepted.")


async def test_registry_never_publishes_a_credential_echoed_in_tool_metadata(monkeypatch):
    from src.services import extensions
    from src.services.app_config import ExtensionConfig

    async def connect(_stack, _config):
        tool = types.Tool(name="echo-fixture-value", inputSchema={"type": "object"})
        return object(), types.ListToolsResult(tools=[tool])

    registry = extensions.ExtensionRegistry()
    monkeypatch.setattr(registry, "_open_and_list", connect)
    try:
        status = await registry.add("outside", ExtensionConfig(
            id="outside", label="Outside", description="", transport="http",
            url="https://outside.example/mcp", headers={"X-Internal-Token": "fixture-value"}))
        assert status.status == "error"
        assert not status.tools and not registry.proxied_tool_definitions()
        assert "fixture-value" not in (status.error or "")
    finally:
        await registry.aclose()


async def test_lost_mcp_worker_removes_its_tools(monkeypatch):
    from src.services import extensions
    from src.services.app_config import ExtensionConfig

    closing = asyncio.Event()

    async def connect(stack, _config):
        group = await stack.enter_async_context(anyio.create_task_group())

        async def remote():
            await closing.wait()
            raise ConnectionError("remote disconnected")

        group.start_soon(remote)
        return object(), types.ListToolsResult(tools=[types.Tool(name="hello", inputSchema={})])

    registry = extensions.ExtensionRegistry()
    monkeypatch.setattr(registry, "_open_and_list", connect)
    try:
        await registry.add("example", ExtensionConfig(id="example", label="Example", description=""))
        assert registry.proxied_tool_definitions()
        closing.set()
        async with asyncio.timeout(0.5):
            while registry.proxied_tool_definitions():
                await asyncio.sleep(0.01)
        assert registry.statuses()[0].status == "error"
    finally:
        await registry.aclose()


def test_rest_probes_reject_wrong_tokens_after_public_health(tmp_path):
    from src.connection_admin import install_connection_admin
    from src.services.connections import ConnectionStore

    def reply(request):
        return httpx.Response(200 if request.url.path == "/health" else 403, json={"ready": True})

    app = Starlette()
    install_auth(app)
    store = ConnectionStore(tmp_path / "settings.db")
    store.update("scribe", {"rest": {"base_url": "http://scribe", "auth": {"kind": "token", "token": "fixture"}}})
    install_connection_admin(app, store, httpx.AsyncClient(transport=httpx.MockTransport(reply)))
    with TestClient(app) as client:
        result = client.post("/admin/connections/scribe/test/rest", headers=FreshHeaders(uid="one", username="ada"))
    assert result.json() == {"ok": False, "message": "REST refused the credentials."}
