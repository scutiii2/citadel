import json
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent.parent / "configs" / "config_extensions.json.example"


def test_bard_example_entry_matches_the_service_defaults():
    entry = json.loads(EXAMPLE.read_text(encoding="utf-8"))["bard"]
    assert entry["url"] == "http://127.0.0.1:8090/mcp"
    assert entry["headers"] == {"X-Internal-Token": "${INTERNAL_API_TOKEN}"}
    assert entry["forward_requester"] is True
    assert "command" not in entry


def test_scribe_example_entry_matches_the_service_defaults():
    entry = json.loads(EXAMPLE.read_text(encoding="utf-8"))["scribe"]
    assert entry["url"] == "http://127.0.0.1:8091/mcp"
    assert entry["headers"] == {"X-Internal-Token": "${INTERNAL_API_TOKEN}"}
    assert entry["forward_requester"] is True
    assert "command" not in entry
