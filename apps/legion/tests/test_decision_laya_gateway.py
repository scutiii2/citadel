import pytest

from src.providers.decision.contract import DecisionError, DecisionRequest
from src.providers.decision.gateways.laya import DEFAULT_STRATEGY, DEFAULT_WINDOW, LayaGateway
from src.providers import llm_config
from src.providers.decision.laya_model import LayaServiceError


class FakeService:
    configured = True

    def __init__(self, body=None, error=None):
        self.body, self.error, self.calls = body, error, []

    def ask(self, strategy, text, questions, max_len, **tuning):
        self.calls.append((strategy, text, questions, max_len, tuning))
        if self.error:
            raise self.error
        return self.body


QUESTION = {"q": {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}}}


def test_uses_configured_strategy_and_passes_min_confidence():
    service = FakeService({"answers": {"q": {"choice": "a", "answer_confidence": 0.95}},
                           "calls": [{"model": "m", "input_tokens": 5, "duration_ms": 1, "ok": True}]})
    result = LayaGateway(service).ask(DecisionRequest("hi", QUESTION, min_confidence=0.8))
    strategy, text, _, max_len, tuning = service.calls[0]
    assert strategy == "english-then-typed" and text == "hi" and max_len == 4096
    assert tuning["min_confidence"] == 0.8
    assert result.answers["q"]["choice"] == "a" and result.tokens == 5


def test_passes_runner_timeout_to_laya_client():
    service = FakeService({"answers": {}})
    LayaGateway(service).ask(DecisionRequest("hi", QUESTION), timeout=2)
    assert service.calls[0][4]["timeout"] == 2


def test_strategy_follows_the_gateway_file_without_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_config, "GATEWAYS_DIR", tmp_path)
    path = tmp_path / "decision" / "laya.json"
    path.parent.mkdir()
    path.write_text('{"strategy": "english-only"}', encoding="utf-8")
    gateway = LayaGateway(FakeService())
    assert gateway.strategy == "english-only"
    path.write_text('{"strategy": "typed-then-english"}', encoding="utf-8")
    assert gateway.strategy == "typed-then-english"


def test_missing_gateway_file_uses_default(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_config, "GATEWAYS_DIR", tmp_path)
    assert LayaGateway(FakeService()).strategy == DEFAULT_STRATEGY


def test_missing_strategy_uses_default(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_config, "GATEWAYS_DIR", tmp_path)
    path = tmp_path / "decision" / "laya.json"
    path.parent.mkdir()
    path.write_text('{}', encoding="utf-8")
    assert LayaGateway(FakeService()).strategy == DEFAULT_STRATEGY


def test_service_error_becomes_decision_error():
    with pytest.raises(DecisionError, match="down"):
        LayaGateway(FakeService(error=LayaServiceError("down"))).ask(DecisionRequest("hi", QUESTION))


def test_text_over_the_window_is_refused():
    with pytest.raises(DecisionError, match="4000"):
        LayaGateway(FakeService({"answers": {}})).ask(DecisionRequest("x" * 4001, QUESTION))


def test_not_available_when_not_configured():
    service = FakeService()
    service.configured = False
    assert LayaGateway(service).available() is False


def test_invalid_gateway_file_is_a_decision_error(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_config, "GATEWAYS_DIR", tmp_path)
    path = tmp_path / "decision" / "laya.json"
    path.parent.mkdir()
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(DecisionError, match="laya.json"):
        LayaGateway(FakeService({"answers": {}})).ask(DecisionRequest("hi", QUESTION))


def test_window_defaults_to_the_old_triage_window(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_config, "GATEWAYS_DIR", tmp_path)
    assert DEFAULT_WINDOW == 4096 and LayaGateway(FakeService()).window == 4096


def test_window_follows_the_gateway_file_and_is_sent_as_max_len(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_config, "GATEWAYS_DIR", tmp_path)
    path = tmp_path / "decision" / "laya.json"
    path.parent.mkdir()
    path.write_text('{"window": 1024}', encoding="utf-8")
    service = FakeService({"answers": {}, "calls": []})
    LayaGateway(service).ask(DecisionRequest("hi", QUESTION))
    assert service.calls[0][3] == 1024
    path.write_text('{"window": 2048}', encoding="utf-8")
    LayaGateway(service).ask(DecisionRequest("hi", QUESTION))
    assert service.calls[1][3] == 2048


@pytest.mark.parametrize("raw", ['"4096"', "8", "9000", "true", "null"])
def test_invalid_window_is_a_decision_error(tmp_path, monkeypatch, raw):
    monkeypatch.setattr(llm_config, "GATEWAYS_DIR", tmp_path)
    path = tmp_path / "decision" / "laya.json"
    path.parent.mkdir()
    path.write_text('{"window": ' + raw + "}", encoding="utf-8")
    with pytest.raises(DecisionError, match="window"):
        LayaGateway(FakeService({"answers": {}})).ask(DecisionRequest("hi", QUESTION))
