from pathlib import Path

from src.runtime.shared_token import shared_token


def test_creates_once_and_reuses(tmp_path, monkeypatch):
    path = tmp_path / "sub" / "internal_token"
    monkeypatch.setenv("INTERNAL_TOKEN_FILE", str(path))
    first = shared_token()
    assert len(first) >= 32
    assert shared_token() == first == path.read_text().strip()
    assert [p.name for p in path.parent.iterdir()] == ["internal_token"]


def test_empty_env_switches_off(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_TOKEN_FILE", "")
    assert shared_token() == ""


def test_unwritable_path_gives_empty(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("INTERNAL_TOKEN_FILE", str(blocker / "internal_token"))
    assert shared_token() == ""
