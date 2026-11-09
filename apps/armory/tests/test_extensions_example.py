import json
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent.parent / "configs" / "config_extensions.json.example"


def test_bard_example_entry_matches_the_service_defaults():
    entry = json.loads(EXAMPLE.read_text(encoding="utf-8"))["bard"]
    assert entry["url"] == "http://127.0.0.1:29400/mcp"
    assert entry["headers"] == {"X-Internal-Token": "${BARD_TOKEN}"}
    assert entry["forward_requester"] is True
    assert "command" not in entry


def test_scribe_example_entry_matches_the_service_defaults():
    entry = json.loads(EXAMPLE.read_text(encoding="utf-8"))["scribe"]
    assert entry["url"] == "http://127.0.0.1:29401/mcp"
    assert entry["headers"] == {"X-Internal-Token": "${SCRIBE_TOKEN}"}
    assert entry["forward_requester"] is True
    assert "command" not in entry


def test_other_tool_services_are_registered_with_their_own_tokens():
    entries = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    for key, port, token in (("ocr", 29402, "READER_TOKEN"), ("lens", 29403, "LENS_TOKEN"), ("mimic", 29404, "MIMIC_TOKEN")):
        entry = entries[key]
        assert entry["url"] == f"http://127.0.0.1:{port}/mcp"
        assert entry["headers"] == {"X-Internal-Token": "${" + token + "}"}
        assert entry["forward_requester"] is True
        assert "command" not in entry
