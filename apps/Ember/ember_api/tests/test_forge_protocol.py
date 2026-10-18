from __future__ import annotations

import json

from src.services.forge.protocol import (
    Delta,
    Hello,
    TurnDone,
    cancel_frame,
    parse_worker_frame,
    permission_reply_frame,
    ready_frame,
    turn_frame,
)


def test_a_valid_worker_frame_is_parsed_into_its_model() -> None:
    frame = parse_worker_frame(json.dumps({"type": "hello", "plan": "Max", "version": "1"}))

    assert isinstance(frame, Hello) and frame.plan == "Max"
    done = parse_worker_frame(json.dumps({"type": "turn_done", "turn_id": "t1", "text": "ok"}))
    assert isinstance(done, TurnDone) and done.text == "ok"


def test_hello_plan_is_optional() -> None:
    frame = parse_worker_frame('{"type": "hello"}')

    assert isinstance(frame, Hello) and frame.plan is None


def test_unknown_types_malformed_json_and_bad_fields_are_ignored() -> None:
    assert parse_worker_frame('{"type": "dance"}') is None
    assert parse_worker_frame("not json") is None
    assert parse_worker_frame('{"type": "delta", "turn_id": "t"}') is None  # text missing
    assert parse_worker_frame('{"type": "delta", "turn_id": "t", "text": 5}') is None


def test_oversized_text_is_refused() -> None:
    raw = json.dumps({"type": "delta", "turn_id": "t", "text": "x" * 20_001})

    assert parse_worker_frame(raw) is None


def test_frames_for_the_worker_match_the_spec() -> None:
    assert ready_frame(3) == {"type": "ready", "worker_id": 3}
    assert permission_reply_frame("r1", True) == {"type": "permission_reply", "request_id": "r1", "allow": True}
    assert cancel_frame("t1") == {"type": "cancel", "turn_id": "t1"}
    assert turn_frame(
        turn_id="t1", group_id=2, folder="C:/w", mode="ask", prompt="hi", history=[{"sender": "user", "text": "a"}]
    ) == {
        "type": "turn",
        "turn_id": "t1",
        "group_id": 2,
        "folder": "C:/w",
        "mode": "ask",
        "prompt": "hi",
        "history": [{"sender": "user", "text": "a"}],
    }


def test_delta_default_type_lets_code_build_frames_directly() -> None:
    assert Delta(turn_id="t", text="x").type == "delta"


def test_browse_frames() -> None:
    from src.services.forge.protocol import BrowseResult, browse_frame

    assert browse_frame("r1", "C:/s") == {"type": "browse", "request_id": "r1", "start": "C:/s"}
    picked = parse_worker_frame('{"type": "browse_result", "request_id": "r1", "path": "C:/x"}')
    assert isinstance(picked, BrowseResult) and picked.path == "C:/x"
    cancelled = parse_worker_frame('{"type": "browse_result", "request_id": "r1"}')
    assert isinstance(cancelled, BrowseResult) and cancelled.path is None
    assert parse_worker_frame('{"type": "browse_result", "path": "C:/x"}') is None  # no request id
