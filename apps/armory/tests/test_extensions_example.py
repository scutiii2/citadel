import json
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent.parent / "configs" / "config_extensions.json"


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


def test_admin_edits_go_to_the_overlay_not_the_tracked_file(tmp_path, monkeypatch):
    import json
    from dataclasses import replace

    from src import config as app_settings
    from src.services import app_config

    configs = tmp_path / "configs"
    configs.mkdir()
    tracked = configs / "config_capabilities.json"
    tracked.write_text(json.dumps({"web": {"enabled": True}, "gen": {"enabled": True}}), encoding="utf-8")
    before = tracked.read_text(encoding="utf-8")
    monkeypatch.setattr(app_settings, "settings", replace(app_settings.settings, configs_dir=configs))
    monkeypatch.setattr(app_settings, "DATA", tmp_path / "data")

    app_config.save_capabilities_config(tracked, "web", False)

    assert tracked.read_text(encoding="utf-8") == before
    overlay = tmp_path / "data" / "config" / "config_capabilities.json"
    assert json.loads(overlay.read_text(encoding="utf-8")) == {"web": {"enabled": False}}
    loaded = app_config.load_capabilities_config(tracked)
    assert not app_config.capability_enabled(loaded, "web") and app_config.capability_enabled(loaded, "gen")
