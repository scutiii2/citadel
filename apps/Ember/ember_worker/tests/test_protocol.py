from __future__ import annotations

import json

from src.events import Failed, Finished, HistoryLine, TextDelta, ToolCall, TurnRequest, UsageReport
from src.protocol import (
    CancelFrame,
    PermissionReply,
    ReadyFrame,
    delta_frames,
    heartbeat_frame,
    hello_frame,
    parse_server_frame,
    permission_request_frame,
    tool_frame,
    turn_done_frame,
    turn_error_frame,
    usage_frame,
)


def test_a_turn_frame_becomes_a_request() -> None:
    raw = json.dumps(
        {
            "type": "turn", "turn_id": "t1", "group_id": 3, "folder": "C:/w", "mode": "ask", "prompt": "fix it",
            "history": [{"sender": "user", "text": "hi"}, {"sender": "codex", "text": "yo"}],
        }
    )

    assert parse_server_frame(raw) == TurnRequest(
        turn_id="t1", group_id=3, folder="C:/w", mode="ask", prompt="fix it",
        history=(HistoryLine("user", "hi"), HistoryLine("codex", "yo")),
    )


def test_the_other_server_frames() -> None:
    assert parse_server_frame('{"type": "ready", "worker_id": 4}') == ReadyFrame(4)
    assert parse_server_frame('{"type": "permission_reply", "request_id": "r", "allow": true}') == PermissionReply("r", True)
    assert parse_server_frame('{"type": "permission_reply", "request_id": "r", "allow": false}') == PermissionReply("r", False)
    assert parse_server_frame('{"type": "cancel", "turn_id": "t"}') == CancelFrame("t")


def test_anything_unusable_is_ignored() -> None:
    for raw in ("nope", "[]", '{"type": "dance"}', '{"type": "turn"}', '{"type": "cancel"}',
                '{"type": "permission_reply", "request_id": "r", "allow": "yes"}', '{"type": "ready", "worker_id": "x"}'):
        assert parse_server_frame(raw) is None, raw


def test_worker_frames_match_the_spec() -> None:
    assert hello_frame("Max", "0.1.0") == {"type": "hello", "plan": "Max", "version": "0.1.0"}
    assert hello_frame(None, "0.1.0")["plan"] is None
    assert heartbeat_frame() == {"type": "heartbeat"}
    assert tool_frame("t", "Bash", "npm test") == {"type": "tool", "turn_id": "t", "name": "Bash", "summary": "npm test"}
    assert permission_request_frame("t", "r", "Bash", "rm x") == {
        "type": "permission_request", "turn_id": "t", "request_id": "r", "tool": "Bash", "summary": "rm x",
    }
    assert usage_frame("t", 5, 7) == {"type": "usage", "turn_id": "t", "input_tokens": 5, "output_tokens": 7}
    assert turn_done_frame("t", "ok") == {"type": "turn_done", "turn_id": "t", "text": "ok"}
    assert turn_error_frame("t", "bad") == {"type": "turn_error", "turn_id": "t", "message": "bad"}


def test_long_fields_are_clipped_to_the_server_limits() -> None:
    assert len(hello_frame("p" * 200, "v" * 200)["plan"]) == 80
    assert len(hello_frame("p", "v" * 200)["version"]) == 40
    assert len(tool_frame("t", "n" * 200, "s" * 900)["name"]) == 80
    assert len(tool_frame("t", "n", "s" * 900)["summary"]) == 500
    assert len(permission_request_frame("t", "r", "n" * 200, "s" * 900)["summary"]) == 500
    assert len(turn_error_frame("t", "e" * 5000)["message"]) == 2000
    assert len(turn_done_frame("t", "x" * 300_000)["text"]) == 200_000


def test_deltas_are_split_into_chunks_the_server_accepts() -> None:
    chunks = delta_frames("t", "a" * 45_000)

    assert [len(c["text"]) for c in chunks] == [20_000, 20_000, 5_000]
    assert all(c["type"] == "delta" and c["turn_id"] == "t" for c in chunks)
    assert delta_frames("t", "") == []


def test_events_are_plain_values() -> None:
    assert TextDelta("a") == TextDelta("a")
    assert Finished("x") != Failed("x")
    assert ToolCall("Bash", "ls").name == "Bash" and UsageReport(1, 2).output_tokens == 2


def test_a_browse_request_and_its_result() -> None:
    from src.protocol import BrowseRequest, browse_result_frame, parse_server_frame

    assert parse_server_frame('{"type": "browse", "request_id": "r", "start": "C:/s"}') == BrowseRequest("r", "C:/s")
    assert parse_server_frame('{"type": "browse", "request_id": "r", "start": null}') == BrowseRequest("r", None)
    assert parse_server_frame('{"type": "browse"}') is None
    assert browse_result_frame("r", "C:/x") == {"type": "browse_result", "request_id": "r", "path": "C:/x"}
    assert browse_result_frame("r", None)["path"] is None
    assert len(browse_result_frame("r", "p" * 900)["path"]) == 500
