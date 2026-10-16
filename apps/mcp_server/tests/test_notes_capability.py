"""The notes capability through its real MCP tools, and its db_gateway client against a local HTTP server."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from mcp.server.fastmcp import FastMCP

from src import capability_help, commands
from src.capabilities.notes.utils.gateway import NotesGateway, NotesGatewayError
from src.config import settings
from src.services import capability_meta, capability_registry, identity_context
from src.services.capability_loader import CapabilityLoader

ALICE, BOB = "uid-alice", "uid-bob"
ID1, ID2, ID3, ID4 = (c * 32 for c in "1234")


def note(key, owner, title, body="", tags=(), shared=True, updated="2026-02-01T10:00:00"):
    return {
        "id": key, "owner": owner, "title": title, "body": body, "tags": list(tags),
        "agent_readable": shared, "created_at": updated, "updated_at": updated,
    }


class FakeGateway:
    """Answers like db_gateway but ignores the filters, so the capability's own checks are what is tested."""

    def __init__(self, docs):
        self.docs = {d["id"]: d for d in docs}
        self.down = False

    def get(self, key):
        self._check()
        return self.docs.get(key)

    def readable_by_agents(self, owner):
        self._check()
        return sorted(self.docs.values(), key=lambda d: d["updated_at"], reverse=True)

    def _check(self):
        if self.down:
            # The loader re-imports the capability, so raise the error class of the live module.
            raise sys.modules["src.capabilities.notes.utils.gateway"].NotesGatewayError("Could not reach db_gateway: refused")


@pytest.fixture
def library():
    return FakeGateway([
        note(ID1, ALICE, "Wifi", "router: blue box\npassword is in the drawer", ["home", "it"], updated="2026-02-02T10:00:00"),
        note(ID2, ALICE, "Diary", "private thoughts", ["home"], shared=False),
        note(ID3, BOB, "Bob's list", "milk and eggs", ["home"], updated="2026-02-03T10:00:00"),
        note(ID4, ALICE, "Budget", "rent is due on the 1st", ["money"], updated="2026-01-01T10:00:00"),
    ])


@pytest.fixture
def capability(tmp_path, monkeypatch, library):
    import src.server

    server = FastMCP("notes-test")
    monkeypatch.setattr(src.server, "mcp", server)
    monkeypatch.setattr(capability_registry, "_REGISTRY", {})
    monkeypatch.setattr(capability_meta, "_BY_FOLDER", {})
    monkeypatch.setattr(commands, "_COMMANDS", {})
    config = tmp_path / "capabilities.json"
    config.write_text("{}")
    loader = CapabilityLoader(server, "src.capabilities", config)
    loader.scan()
    asyncio.run(loader.set_online("notes", True))
    domain = sys.modules["src.capabilities.notes.domain"]
    # Pin the exposure inputs, so a developer's MCP_HOST or token in .env cannot change the result.
    monkeypatch.setattr(
        domain, "settings", dataclasses.replace(settings, host="127.0.0.1", internal_api_token="")
    )
    monkeypatch.setattr(domain, "open_gateway", lambda: library)
    monkeypatch.setattr(identity_context, "current_uid", lambda: ALICE)
    return server


def call(server, name, args=None):
    return asyncio.run(server.call_tool(name, args or {}))


def structured(result):
    return result[1]  # FastMCP returns (content, structured content) for typed models


def test_list_shows_only_my_shared_notes_newest_first(capability):
    found = structured(call(capability, "tool_notes_listNotes"))

    assert [n["title"] for n in found["notes"]] == ["Wifi", "Budget"]  # not Diary (switch off), not Bob's
    assert found["count"] == 2
    first = found["notes"][0]
    assert (first["id"], first["tags"], first["updated"]) == (ID1, "home, it", "2026-02-02")
    assert first["preview"] == "router: blue box password is in the drawer"


def test_list_can_be_filtered_by_tag(capability):
    assert [n["title"] for n in structured(call(capability, "tool_notes_listNotes", {"tag": " MONEY "}))["notes"]] == ["Budget"]
    none = structured(call(capability, "tool_notes_listNotes", {"tag": "travel"}))
    assert none["count"] == 0 and "travel" in none["message"]


def test_list_with_nothing_shared_says_so(capability, monkeypatch):
    monkeypatch.setattr(identity_context, "current_uid", lambda: "uid-nobody")

    found = structured(call(capability, "tool_notes_listNotes"))

    assert found == {"count": 0, "notes": [], "message": "No notes are shared with agents."}


def test_search_matches_titles_and_lines_and_ignores_unshared_and_foreign_notes(capability):
    by_line = structured(call(capability, "tool_notes_searchNotes", {"query": "DRAWER"}))
    assert [(h["id"], h["line"]) for h in by_line["hits"]] == [(ID1, "password is in the drawer")]

    by_title = structured(call(capability, "tool_notes_searchNotes", {"query": "budget"}))
    assert [(h["title"], h["line"]) for h in by_title["hits"]] == [("Budget", "Budget")]

    for secret in ("private thoughts", "milk"):  # Diary is switched off, the other is Bob's
        assert structured(call(capability, "tool_notes_searchNotes", {"query": secret}))["count"] == 0


def test_search_needs_a_query(capability):
    with pytest.raises(Exception, match="Say what to search for"):
        call(capability, "tool_notes_searchNotes", {"query": "   "})


def test_read_returns_the_note_fenced_as_data(capability):
    result = structured(call(capability, "tool_notes_readNote", {"note_id": ID1.upper()}))

    assert (result["id"], result["title"], result["tags"]) == (ID1, "Wifi", "home, it")
    assert "data, not instructions" in result["content"]
    assert "password is in the drawer" in result["content"]
    assert result["content"].index("BEGIN REMOTE OUTPUT") < result["content"].index("router") < result["content"].index("END REMOTE OUTPUT")


@pytest.mark.parametrize("note_id", [ID2, ID3, "9" * 32, "../etc/passwd", "nope", ""])
def test_a_note_that_is_off_foreign_missing_or_malformed_is_just_not_available(capability, note_id):
    with pytest.raises(Exception, match="No note with that id is available to agents"):
        call(capability, "tool_notes_readNote", {"note_id": note_id})


def test_a_gateway_that_ignores_its_filters_cannot_leak_a_note(capability, library):
    # readable_by_agents() of the fake returns every document, Bob's and the switched-off ones included.
    assert len(library.readable_by_agents(ALICE)) == 4

    titles = [n["title"] for n in structured(call(capability, "tool_notes_listNotes"))["notes"]]

    assert titles == ["Wifi", "Budget"]


def test_every_tool_refuses_without_an_identity(capability, monkeypatch):
    monkeypatch.setattr(identity_context, "current_uid", lambda: "")
    monkeypatch.setattr(identity_context, "current_username", lambda: "alice")  # a name alone is not enough

    for name, args in (
        ("tool_notes_listNotes", {}),
        ("tool_notes_searchNotes", {"query": "wifi"}),
        ("tool_notes_readNote", {"note_id": ID1}),
    ):
        with pytest.raises(Exception, match="signed-in user"):
            call(capability, name, args)


def test_every_tool_refuses_when_the_server_is_exposed_without_a_token(capability, monkeypatch):
    domain = sys.modules["src.capabilities.notes.domain"]
    monkeypatch.setattr(domain, "settings", dataclasses.replace(domain.settings, host="0.0.0.0", internal_api_token=""))

    for name, args in (
        ("tool_notes_listNotes", {}),
        ("tool_notes_searchNotes", {"query": "wifi"}),
        ("tool_notes_readNote", {"note_id": ID1}),
    ):
        with pytest.raises(Exception, match="INTERNAL_API_TOKEN"):
            call(capability, name, args)


def test_it_works_on_an_exposed_host_once_a_token_is_set(capability, monkeypatch):
    domain = sys.modules["src.capabilities.notes.domain"]
    monkeypatch.setattr(domain, "settings", dataclasses.replace(domain.settings, host="0.0.0.0", internal_api_token="secret"))

    assert structured(call(capability, "tool_notes_listNotes"))["count"] == 2


def test_an_unreachable_gateway_is_a_clear_error(capability, library):
    library.down = True

    for name, args in (
        ("tool_notes_listNotes", {}),
        ("tool_notes_searchNotes", {"query": "x"}),
        ("tool_notes_readNote", {"note_id": ID1}),
    ):
        with pytest.raises(Exception, match="Notes are unavailable right now"):
            call(capability, name, args)


def test_tools_commands_and_help_follow_the_contract(capability):
    tools = {tool.name: tool for tool in asyncio.run(capability.list_tools())}
    assert set(tools) == {"tool_notes_listNotes", "tool_notes_searchNotes", "tool_notes_readNote"}
    assert all((tool.meta or {}).get("display_label") for tool in tools.values())
    assert all(tool.annotations and tool.annotations.readOnlyHint for tool in tools.values())
    for tool in tools.values():
        for prop in tool.inputSchema["properties"].values():
            assert prop.get("description")
        assert "uid" not in tool.inputSchema["properties"] and "owner" not in tool.inputSchema["properties"]
    help_result = capability_help.build_help("notes", target="all")
    assert {row["slash_command"] for row in help_result["commands"]} == {"/notes list", "/notes search", "/notes read"}
    assert not any((tool.meta or {}).get("ai_explain_result") for tool in tools.values())


# ---- the db_gateway client, against a real local HTTP server ----


class _Handler(BaseHTTPRequestHandler):
    seen: list[dict] = []
    docs: dict[str, dict] = {}

    def _answer(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _record(self, body=None):
        self.seen.append({"method": self.command, "path": self.path, "token": self.headers.get("X-Internal-Token"), "body": body})

    def do_GET(self):
        self._record()
        key = self.path.rsplit("/", 1)[1]
        if key in self.docs:
            return self._answer(200, {"doc": self.docs[key]})
        if key == "boom":
            return self._answer(500, {"error": "database is on fire"})
        self._answer(404, {"error": f"no record {key!r} in 'notes'"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._record(body)
        owner = body["filters"]["owner"]
        self._answer(200, {"docs": [d for d in self.docs.values() if d["owner"] == owner and d["agent_readable"]]})

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    _Handler.seen = []
    _Handler.docs = {d["id"]: d for d in (note(ID1, ALICE, "A", updated="2026-01-01T00:00:00"), note(ID4, ALICE, "B", updated="2026-03-01T00:00:00"))}
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", _Handler
    httpd.shutdown()
    httpd.server_close()


def test_the_client_queries_the_right_collection_with_the_token_and_filters(server):
    url, handler = server

    docs = NotesGateway(url + "/", "mcp_server", "data", "secret").readable_by_agents(ALICE)

    assert [d["title"] for d in docs] == ["B", "A"]  # newest edit first
    seen = handler.seen[0]
    assert seen["method"] == "POST"
    assert seen["path"] == "/instances/mcp_server/connections/data/collections/notes/query"
    assert seen["token"] == "secret"
    assert seen["body"] == {"filters": {"owner": ALICE, "agent_readable": True}, "limit": 200, "offset": 0}


def test_the_client_reads_one_record_and_reports_a_missing_one_as_none(server):
    url, handler = server
    client = NotesGateway(url, "mcp_server", "data", "")

    assert client.get(ID1)["title"] == "A"
    assert client.get("9" * 32) is None
    assert handler.seen[0]["token"] is None  # no token configured: none sent


def test_the_client_turns_failures_into_one_error(server):
    url, _ = server

    with pytest.raises(NotesGatewayError, match="HTTP 500: database is on fire"):
        NotesGateway(url, "mcp_server", "data", "").get("boom")
    with pytest.raises(NotesGatewayError, match="Could not reach db_gateway"):
        NotesGateway("http://127.0.0.1:1", "mcp_server", "data", "", timeout=1).get(ID1)


def test_the_client_encodes_names_so_they_cannot_change_the_path(server):
    url, handler = server

    NotesGateway(url, "a/b", "c d", "").get("../x")

    assert handler.seen[0]["path"] == "/instances/a%2Fb/connections/c%20d/collections/notes/records/..%2Fx"
