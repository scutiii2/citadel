"""The notes capability (read and write) through its real MCP tools, and its db_gateway client against a local HTTP server."""

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
        doc = self.docs.get(key)
        return None if doc is None else json.loads(json.dumps(doc))

    def put(self, key, doc):
        self._check()
        self.docs[key] = json.loads(json.dumps(doc))

    def count_owned(self, owner):
        self._check()
        return sum(1 for d in self.docs.values() if d["owner"] == owner)

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
    reads = {"tool_notes_listNotes", "tool_notes_searchNotes", "tool_notes_readNote"}
    writes = {"tool_notes_createNote", "tool_notes_updateNote", "tool_notes_appendToNote"}
    assert set(tools) == reads | writes
    assert all((tool.meta or {}).get("display_label") for tool in tools.values())
    assert all(tools[name].annotations.readOnlyHint is True for name in reads)
    assert all(tools[name].annotations.readOnlyHint is False for name in writes)
    assert not [name for name in tools if "delete" in name.lower() or "forget" in name.lower()]  # agents never delete
    for tool in tools.values():
        for prop in tool.inputSchema["properties"].values():
            assert prop.get("description")
        assert "uid" not in tool.inputSchema["properties"] and "owner" not in tool.inputSchema["properties"]
    help_result = capability_help.build_help("notes", target="all")
    assert {row["slash_command"] for row in help_result["commands"]} == {
        "/notes list", "/notes search", "/notes read", "/notes create", "/notes update", "/notes append",
    }
    assert not any((tool.meta or {}).get("ai_explain_result") for tool in tools.values())


# ---- writing ----


def stored(library, key):
    return library.docs[key]


def test_create_stores_a_note_ember_can_open_and_the_agent_can_read_back(capability, library):
    made = structured(call(capability, "tool_notes_createNote", {
        "title": "  Sci-fi picks ", "body": "Arrival\nPrimer", "tags": " Movies, sci-fi ,movies,",
    }))

    doc = stored(library, made["id"])
    assert (doc["title"], doc["body"], doc["tags"]) == ("Sci-fi picks", "Arrival\nPrimer", ["movies", "sci-fi"])
    assert (doc["owner"], doc["agent_readable"], doc["last_editor"]) == (ALICE, True, "agent")
    assert doc["created_at"] == doc["updated_at"] and len(doc["created_at"]) == 19  # 2026-10-16T10:00:00, as ember writes it
    assert set(doc) == {"id", "owner", "title", "body", "tags", "agent_readable", "last_editor", "created_at", "updated_at"}
    assert made["tags"] == "movies, sci-fi" and made["id"] == doc["id"] and len(made["id"]) == 32
    assert "last edited by an agent" in made["message"]
    # Shared from the start, so the agent's own list and read already show it.
    assert made["id"] in [n["id"] for n in structured(call(capability, "tool_notes_listNotes"))["notes"]]
    assert "Primer" in structured(call(capability, "tool_notes_readNote", {"note_id": made["id"]}))["content"]


@pytest.mark.parametrize("args, message", [
    ({"title": "   ", "body": "x"}, "needs a title"),
    ({"title": "x" * 201, "body": "x"}, "at most 200 characters"),
    ({"title": "ok", "body": "x" * 20_001}, "at most 20000 characters"),
    ({"title": "ok", "body": "x", "tags": "two words"}, "not allowed"),
    ({"title": "ok", "body": "x", "tags": "-lead"}, "not allowed"),
    ({"title": "ok", "body": "x", "tags": "x" * 31}, "not allowed"),
    ({"title": "ok", "body": "x", "tags": ",".join(f"t{i}" for i in range(11))}, "at most 10 tags"),
])
def test_create_refuses_what_ember_would_refuse(capability, library, args, message):
    before = dict(library.docs)

    with pytest.raises(Exception, match=message):
        call(capability, "tool_notes_createNote", args)

    assert library.docs == before


def test_create_accepts_the_limits_exactly(capability, library):
    tags = ",".join(["x" * 30] + [f"t{i}" for i in range(9)])

    made = structured(call(capability, "tool_notes_createNote", {"title": "t" * 200, "body": "b" * 20_000, "tags": tags}))

    assert len(stored(library, made["id"])["tags"]) == 10


def test_create_stops_at_the_note_limit(capability, library):
    for i in range(200 - 3):  # Alice already has 3 (one switched off)
        key = f"{i + 100:032x}"
        library.docs[key] = note(key, ALICE, f"n{i}", shared=False)
    assert library.count_owned(ALICE) == 200

    with pytest.raises(Exception, match="already has 200 notes"):
        call(capability, "tool_notes_createNote", {"title": "one too many", "body": "x"})


def test_update_changes_only_the_parts_that_are_given(capability, library):
    result = structured(call(capability, "tool_notes_updateNote", {"note_id": ID1, "body": "new text"}))

    doc = stored(library, ID1)
    assert (doc["title"], doc["body"], doc["tags"]) == ("Wifi", "new text", ["home", "it"])  # title and tags kept
    assert doc["last_editor"] == "agent" and doc["updated_at"] > "2026-02-02T10:00:00" and doc["created_at"] == "2026-02-02T10:00:00"
    assert (doc["owner"], doc["agent_readable"]) == (ALICE, True)  # the switch and the owner never change
    assert result["title"] == "Wifi"

    structured(call(capability, "tool_notes_updateNote", {"note_id": ID1, "title": "Home wifi", "tags": "network, home"}))
    after = stored(library, ID1)
    assert (after["title"], after["tags"], after["body"]) == ("Home wifi", ["network", "home"], "new text")


def test_update_with_nothing_to_change_is_refused(capability):
    with pytest.raises(Exception, match="Nothing to change"):
        call(capability, "tool_notes_updateNote", {"note_id": ID1, "title": " ", "body": "", "tags": ""})


def test_update_refuses_bad_values_without_changing_the_note(capability, library):
    before = dict(stored(library, ID1))

    for args in ({"title": "x" * 201}, {"body": "x" * 20_001}, {"tags": "bad tag"}):
        with pytest.raises(Exception):
            call(capability, "tool_notes_updateNote", {"note_id": ID1, **args})

    assert stored(library, ID1) == before


def test_append_adds_to_the_end_and_keeps_the_rest(capability, library):
    result = structured(call(capability, "tool_notes_appendToNote", {"note_id": ID1, "text": "wifi name: Home5G"}))

    doc = stored(library, ID1)
    assert doc["body"] == "router: blue box\npassword is in the drawer\nwifi name: Home5G"
    assert (doc["title"], doc["tags"], doc["last_editor"]) == ("Wifi", ["home", "it"], "agent")
    assert "Added to" in result["message"]


def test_append_to_an_empty_note_and_around_trailing_newlines(capability, library):
    library.docs[ID1]["body"] = ""
    call(capability, "tool_notes_appendToNote", {"note_id": ID1, "text": "first"})
    assert stored(library, ID1)["body"] == "first"

    library.docs[ID1]["body"] = "list\n\n"
    call(capability, "tool_notes_appendToNote", {"note_id": ID1, "text": "- item"})
    assert stored(library, ID1)["body"] == "list\n- item"


def test_append_leaves_out_list_items_the_note_already_has_and_says_how_many(capability, library):
    library.docs[ID1]["body"] = "- Metropolis\n* Blade Runner\n1. Brazil"

    result = structured(call(capability, "tool_notes_appendToNote", {
        "note_id": ID1, "text": "- metropolis\n- BLADE   runner\n- Gattaca\n- Brazil\n- Gattaca",
    }))

    assert stored(library, ID1)["body"] == "- Metropolis\n* Blade Runner\n1. Brazil\n- Gattaca"
    assert "4 item(s) already in it were left out" in result["message"]


def test_append_keeps_every_line_that_is_not_a_list_item(capability, library):
    library.docs[ID1]["body"] = "---\nintro\n- item"

    result = structured(call(capability, "tool_notes_appendToNote", {"note_id": ID1, "text": "---\nintro\n- item\n- new"}))

    assert stored(library, ID1)["body"] == "---\nintro\n- item\n---\nintro\n- new"
    assert "1 item(s) already in it were left out" in result["message"]


def test_append_of_only_known_items_changes_nothing(capability, library):
    library.docs[ID1]["body"] = "- one\n- two"
    before = dict(stored(library, ID1))

    result = structured(call(capability, "tool_notes_appendToNote", {"note_id": ID1, "text": "- two\n- one"}))

    assert stored(library, ID1) == before
    assert "Nothing added" in result["message"] and "all 2 item(s)" in result["message"]


def test_append_without_repeats_says_nothing_about_them(capability, library):
    result = structured(call(capability, "tool_notes_appendToNote", {"note_id": ID1, "text": "- brand new"}))
    assert "left out" not in result["message"]


def test_append_refuses_empty_text_and_a_note_that_would_overflow(capability, library):
    with pytest.raises(Exception, match="the text is empty"):
        call(capability, "tool_notes_appendToNote", {"note_id": ID1, "text": "  \n"})
    library.docs[ID1]["body"] = "x" * 19_990

    with pytest.raises(Exception, match="would pass 20000 characters"):
        call(capability, "tool_notes_appendToNote", {"note_id": ID1, "text": "y" * 20})

    assert len(stored(library, ID1)["body"]) == 19_990


@pytest.mark.parametrize("note_id", [ID2, ID3, "9" * 32, "../etc", ""])
def test_update_and_append_cannot_touch_a_note_that_is_off_foreign_or_missing(capability, library, note_id):
    before = json.loads(json.dumps(library.docs))

    with pytest.raises(Exception, match="No note with that id is available to agents"):
        call(capability, "tool_notes_updateNote", {"note_id": note_id, "body": "hacked"})
    with pytest.raises(Exception, match="No note with that id is available to agents"):
        call(capability, "tool_notes_appendToNote", {"note_id": note_id, "text": "hacked"})

    assert library.docs == before  # Diary (off) and Bob's note are exactly as they were


def test_a_write_cannot_switch_a_note_on_or_hand_it_to_someone_else(capability, library):
    call(capability, "tool_notes_updateNote", {"note_id": ID1, "title": "t"})
    call(capability, "tool_notes_appendToNote", {"note_id": ID1, "text": "t"})
    made = structured(call(capability, "tool_notes_createNote", {"title": "n", "body": "b"}))

    assert stored(library, ID2)["agent_readable"] is False  # the Diary is still off
    assert stored(library, ID1)["owner"] == ALICE and stored(library, made["id"])["owner"] == ALICE


def test_the_write_tools_take_no_owner_or_switch_parameter(capability):
    for tool in asyncio.run(capability.list_tools()):
        names = set(tool.inputSchema["properties"])
        assert not names & {"uid", "owner", "agent_readable", "shared", "delete"}, tool.name


def test_every_write_tool_refuses_without_an_identity_or_on_an_exposed_host(capability, library, monkeypatch):
    calls = (
        ("tool_notes_createNote", {"title": "t", "body": "b"}),
        ("tool_notes_updateNote", {"note_id": ID1, "body": "b"}),
        ("tool_notes_appendToNote", {"note_id": ID1, "text": "b"}),
    )
    before = json.loads(json.dumps(library.docs))
    monkeypatch.setattr(identity_context, "current_uid", lambda: "")
    for name, args in calls:
        with pytest.raises(Exception, match="signed-in user"):
            call(capability, name, args)
    monkeypatch.setattr(identity_context, "current_uid", lambda: ALICE)
    domain = sys.modules["src.capabilities.notes.domain"]
    monkeypatch.setattr(domain, "settings", dataclasses.replace(domain.settings, host="0.0.0.0", internal_api_token=""))
    for name, args in calls:
        with pytest.raises(Exception, match="INTERNAL_API_TOKEN"):
            call(capability, name, args)

    assert library.docs == before


def test_an_unreachable_gateway_leaves_the_notes_alone_and_says_so(capability, library):
    before = json.loads(json.dumps(library.docs))
    library.down = True

    for name, args in (
        ("tool_notes_createNote", {"title": "t", "body": "b"}),
        ("tool_notes_updateNote", {"note_id": ID1, "body": "b"}),
        ("tool_notes_appendToNote", {"note_id": ID1, "text": "b"}),
    ):
        with pytest.raises(Exception, match="Notes are unavailable right now"):
            call(capability, name, args)
    library.down = False

    assert library.docs == before


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
        filters = body["filters"]
        self._answer(200, {"docs": [d for d in self.docs.values() if all(d.get(k) == v for k, v in filters.items())]})

    def do_PUT(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._record(body)
        self.docs[self.path.rsplit("/", 1)[1]] = body["doc"]
        self._answer(200, {"ok": True})

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


def test_the_client_puts_a_record_and_counts_a_users_notes(server):
    url, handler = server
    client = NotesGateway(url, "mcp_server", "data", "secret")

    client.put(ID2, note(ID2, ALICE, "new", shared=False))  # counted although agents cannot read it
    assert client.count_owned(ALICE) == 3  # the two seeded notes and this one

    put, query = handler.seen
    assert (put["method"], put["path"], put["token"]) == (
        "PUT", f"/instances/mcp_server/connections/data/collections/notes/records/{ID2}", "secret",
    )
    assert put["body"]["doc"]["title"] == "new"
    assert query["body"] == {"filters": {"owner": ALICE}, "limit": 200, "offset": 0}
