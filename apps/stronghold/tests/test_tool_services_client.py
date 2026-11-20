from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from src.tool_services import client as client_module
from src.tool_services.client import ToolServices
from src.tool_services.store import ToolStore

ADDRESS = {"o1": "http://one:1", "o2": "http://two:2"}
FID = "a" * 32


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(client_module, "current_requester",
                        lambda: SimpleNamespace(uid="u-1", username="ana", email="ana@example.com"))
    store = ToolStore(tmp_path / "settings.db")
    store.put("bard", {"enabled": True, "service_id": "s", "token": "parent",
                       "origins": [{"origin_id": "o1"}, {"origin_id": "o2", "header_value": "second"}]})
    state = {"seen": [], "down": set(), "timeout": set(), "clock": 100.0,
             "reply": lambda request: httpx.Response(200, json={"file_id": FID, "duration_s": 1.0, "voice": "v"})}

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host in state["down"]:
            raise httpx.ConnectError("refused")
        if host in state["timeout"]:
            raise httpx.ReadTimeout("slow")
        state["seen"].append((host, request.url.path, request.headers.get("x-internal-token")))
        assert request.headers["x-requester-username"] == "ana"
        assert request.headers["x-requester-email"] == "ana@example.com"
        assert request.headers["x-requester-uid"] == "u-1"
        return state["reply"](request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    services = ToolServices(store, http, ADDRESS.__getitem__, clock=lambda: state["clock"])
    return services, state, store


async def test_speak_goes_to_the_first_origin_with_the_parent_token_and_the_requester(world):
    services, state, _ = world
    result = await services.call("POST", "/connections/bard/speak", {"text": "hi", "voice": None})
    assert result["file_id"] == FID
    assert state["seen"] == [("one", "/api/speak", "parent")]


async def test_a_refused_connection_moves_to_the_next_origin_with_its_override(world):
    services, state, _ = world
    state["down"].add("one")
    await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert state["seen"] == [("two", "/api/speak", "second")]


async def test_a_timeout_fails_the_call_without_trying_another_origin_and_the_next_call_skips_it(world):
    services, state, _ = world
    state["timeout"].add("one")
    with pytest.raises(HTTPException) as error:
        await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert error.value.status_code == 502 and error.value.detail.startswith("[1002]")
    assert state["seen"] == []
    state["timeout"].clear()
    await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert state["seen"] == [("two", "/api/speak", "second")]     # one is cooling down
    state["clock"] += 31
    await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert state["seen"][-1][0] == "one"


async def test_a_call_about_a_file_goes_to_the_origin_that_holds_it(world):
    services, state, _ = world
    state["down"].add("one")
    await services.call("POST", "/connections/bard/speak", {"text": "hi"})   # made on "two"
    state["down"].clear()
    state["clock"] += 31
    response = await services.open_audio(FID, None)
    await response.aclose()
    assert state["seen"][-1] == ("two", f"/api/files/{FID}", "second")


async def test_a_not_ready_service_says_what_to_do(world):
    services, state, _ = world
    with pytest.raises(HTTPException) as error:
        await services.call("POST", "/connections/scribe/transcribe", None)
    assert error.value.status_code == 502 and error.value.detail == "Configure Scribe in Stronghold Admin."
    assert state["seen"] == []


@pytest.mark.parametrize("status, expected", [(400, 400), (413, 413), (401, 502), (403, 502), (503, 502)])
async def test_the_services_answer_maps_to_the_callers_status(world, status, expected):
    services, state, _ = world
    state["reply"] = lambda request: httpx.Response(status, json={"message": "no (parent)"})
    with pytest.raises(HTTPException) as error:
        await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert error.value.status_code == expected
    assert "parent" not in error.value.detail
    assert len(state["seen"]) == 1
    if status in (400, 413):
        assert error.value.detail == "no ([redacted])"
    if status in (401, 403):
        assert "Stronghold Admin" in error.value.detail


async def test_a_file_upload_sends_the_filename_and_bytes(world):
    services, state, store = world
    store.put("scribe", {"enabled": True, "service_id": "s", "token": "t", "origins": [{"origin_id": "o1"}]})
    seen = {}

    def reply(request):
        seen["name"], seen["body"] = request.headers["x-filename"], request.content
        return httpx.Response(200, json={"file_id": FID, "duration_s": 1.0, "expires_at": 9.0})

    state["reply"] = reply
    await services.post_file("/connections/scribe/files", "a.mp3", b"abc")
    assert seen == {"name": "a.mp3", "body": b"abc"}
    with pytest.raises(HTTPException) as error:
        await services.post_file("/connections/scribe/files", "../x", b"abc")
    assert error.value.status_code == 400


async def test_the_token_is_redacted_from_a_result(world):
    services, state, _ = world
    state["reply"] = lambda request: httpx.Response(200, json={"voices": ["v-parent"]})
    assert await services.call("GET", "/connections/bard/voices") == {"voices": ["v-[redacted]"]}

async def test_unknown_files_are_never_sent_to_any_origin(world):
    services, state, _ = world
    with pytest.raises(HTTPException) as error:
        await services.open_audio(FID, None)
    assert error.value.status_code == 404
    assert state["seen"] == []


async def test_a_read_error_during_the_body_cools_the_origin_without_replaying(world):
    services, state, _ = world

    class BrokenBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise httpx.ReadTimeout("body stalled")
            yield b""  # pragma: no cover

    state["reply"] = lambda _: httpx.Response(200, stream=BrokenBody())
    with pytest.raises(HTTPException) as error:
        await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert error.value.status_code == 502 and error.value.detail.startswith("[1002]")
    assert state["seen"] == [("one", "/api/speak", "parent")]
    state["reply"] = lambda _: httpx.Response(200, json={"file_id": FID})
    await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    assert state["seen"][-1] == ("two", "/api/speak", "second")


async def test_audio_does_not_retry_if_its_own_origin_is_unreachable(world):
    services, state, _ = world
    await services.call("POST", "/connections/bard/speak", {"text": "hi"})
    state["down"].add("one")
    with pytest.raises(HTTPException) as error:
        await services.open_audio(FID, None)
    assert error.value.status_code == 502 and error.value.detail.startswith("[1002]")
    assert state["seen"] == [("one", "/api/speak", "parent")]
