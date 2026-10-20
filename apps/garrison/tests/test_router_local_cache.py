from types import SimpleNamespace

import pytest

from src.agents import router_models
from src.llm.laya_provider import LayaQuestions


def test_missing_cache_refuses_load_instead_of_downloading(monkeypatch):
    calls = []
    def missing(checkpoint):
        raise RuntimeError("Router checkpoint is not cached")
    monkeypatch.setattr(router_models, "cached_checkpoint", missing)
    monkeypatch.setitem(__import__("sys").modules, "laya", SimpleNamespace(load=lambda *args: calls.append(args)))
    model = LayaQuestions(local_only=True)
    with pytest.raises(RuntimeError, match="cached"):
        model._load()
    assert not calls


def test_router_loads_absolute_cached_directory_only(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(router_models, "cached_checkpoint", lambda checkpoint: str(tmp_path))
    monkeypatch.setitem(__import__("sys").modules, "laya", SimpleNamespace(load=lambda path: calls.append(path) or object()))
    LayaQuestions(local_only=True)._load()
    assert calls == [str(tmp_path)]


def test_cache_probe_is_local_only_and_rejects_partial_snapshot(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(router_models, "_snapshot", lambda checkpoint: calls.append(checkpoint) or tmp_path)
    with pytest.raises(RuntimeError, match="cached"):
        router_models.cached_checkpoint("typed-decisions")
    for name in ("rl_agent_config.json", "model.safetensors", "encoder/config.json", "tokenizer/tokenizer.json"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    assert router_models.cached_checkpoint("typed-decisions") == str(tmp_path.resolve())


def test_hub_resolution_explicitly_forbids_downloads(monkeypatch, tmp_path):
    import sys

    calls = []
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(
        snapshot_download=lambda **kwargs: calls.append(kwargs) or str(tmp_path)))
    monkeypatch.setitem(sys.modules, "laya.router", SimpleNamespace(
        resolve_model_spec=lambda checkpoint: ("repo/model", "typed-decisions")))
    monkeypatch.setitem(sys.modules, "laya.revisions", SimpleNamespace(resolve_revision=lambda *args: "revision"))
    assert router_models._snapshot("typed-decisions") == tmp_path / "typed-decisions"
    assert calls == [{"repo_id": "repo/model", "revision": "revision", "local_files_only": True, "token": False}]
