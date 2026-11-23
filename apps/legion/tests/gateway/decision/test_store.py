import json

import pytest

from src.gateway.decision.store import GatewayStore


@pytest.fixture
def store(tmp_path):
    return GatewayStore(tmp_path / "gateways.json")


def test_put_returns_public_entry_without_secrets(store, tmp_path):
    entry = store.put("jev", {"kind": "typesafe", "api_key": "sk-secret", "model": "jev-latest"})
    assert entry == {"id": "jev", "kind": "typesafe", "url": "https://api.typesafe.ai/v1/systemone",
                     "model": "jev-latest", "timeout_s": 60, "has_api_key": True}
    assert "sk-secret" not in json.dumps(store.public())
    assert store.all()["jev"]["api_key"] == "sk-secret"
    assert (tmp_path / "gateways.json").exists()


def test_omitted_secret_keeps_the_saved_one(store):
    store.put("jev", {"kind": "typesafe", "api_key": "sk-secret", "model": "jev-latest"})
    store.put("jev", {"kind": "typesafe", "model": "jev-preview"})
    assert store.all()["jev"]["api_key"] == "sk-secret" and store.all()["jev"]["model"] == "jev-preview"


def test_kinds_and_required_fields(store):
    with pytest.raises(ValueError, match="kind"):
        store.put("x", {"kind": "magic"})
    with pytest.raises(ValueError, match="API key"):
        store.put("jev", {"kind": "typesafe", "model": "m"})
    with pytest.raises(ValueError, match="model"):
        store.put("d3", {"kind": "ollama", "url": "http://127.0.0.1:11434"})
    with pytest.raises(ValueError, match="address"):
        store.put("d3", {"kind": "ollama", "model": "d3:2b"})
    store.put("d3", {"kind": "ollama", "url": "http://127.0.0.1:11434/", "model": "d3:2b"})
    assert store.all()["d3"]["url"] == "http://127.0.0.1:11434"
    store.put("laya", {"kind": "scuti", "url": "http://127.0.0.1:29220", "token": "t", "strategy": "auto", "window": 4096})
    assert store.public()[-1]["has_token"] is True


@pytest.mark.parametrize("bad_id", ["", "Jev", "-x", "a b", "x" * 49])
def test_bad_ids(store, bad_id):
    with pytest.raises(ValueError, match="id"):
        store.put(bad_id, {"kind": "scuti", "url": "http://127.0.0.1:1"})


def test_bad_url_timeout_window(store):
    with pytest.raises(ValueError, match="address"):
        store.put("a", {"kind": "scuti", "url": "ftp://x"})
    with pytest.raises(ValueError, match="address"):
        store.put("a", {"kind": "scuti", "url": "http://user:pw@host"})
    with pytest.raises(ValueError, match="timeout"):
        store.put("a", {"kind": "scuti", "url": "http://h:1", "timeout_s": 0})
    with pytest.raises(ValueError, match="window"):
        store.put("a", {"kind": "scuti", "url": "http://h:1", "window": 5})


def test_delete(store):
    store.put("a", {"kind": "scuti", "url": "http://h:1"})
    assert store.delete("a") is True and store.delete("a") is False and store.all() == {}


def test_corrupt_file_reads_as_empty(tmp_path):
    path = tmp_path / "gateways.json"
    path.write_text("{not json", "utf-8")
    assert GatewayStore(path).all() == {}
