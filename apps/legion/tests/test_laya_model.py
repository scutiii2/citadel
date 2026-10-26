"""LAYAModel talks to the shared Laya service and nothing else."""

import httpx
import pytest

from src.providers.decision import laya_model
from src.providers.decision.laya_model import LAYAModel, LayaServiceError

QUESTIONS = {"q": {"type": "noul", "instructions": "Fine?"}}
ANSWER = {"answers": {"q": {"noul": 0.9}}, "calls": []}


def post_returning(monkeypatch, response, sent):
    def post(url, **kwargs):
        sent.append((url, kwargs))
        return response(url) if callable(response) else response

    monkeypatch.setattr(laya_model.httpx, "post", post)


def ok(url, body=ANSWER):
    return httpx.Response(200, json=body, request=httpx.Request("POST", url))


def test_ask_sends_the_strategy_token_and_tuning_and_asks_for_the_trace(monkeypatch):
    sent = []
    post_returning(monkeypatch, ok, sent)
    agent = LAYAModel("http://laya:9120/", "tok")
    assert agent.ask("typed-only", "text", QUESTIONS, 4096, min_confidence=0.6, prune_ratio=None) == ANSWER
    url, kwargs = sent[0]
    assert url == "http://laya:9120/v1/ask" and kwargs["headers"] == {"X-Internal-Token": "tok"}
    assert kwargs["json"] == {"strategy": "typed-only", "text": "text", "questions": QUESTIONS, "max_len": 4096,
                              "trace": True, "min_confidence": 0.6}


def test_combine_posts_the_voters(monkeypatch):
    sent = []
    post_returning(monkeypatch, lambda url: ok(url, {"kept": ["a", "b"]}), sent)
    assert LAYAModel("http://laya:9120").combine({"jev": {}}, ["a", "b"], 0.25, 0.5) == {"kept": ["a", "b"]}
    assert sent[0][0].endswith("/v1/combine") and sent[0][1]["json"]["options"] == ["a", "b"]
    assert sent[0][1]["headers"] == {}


def test_a_refused_request_carries_the_calls_the_service_made(monkeypatch):
    detail = {"detail": {"message": "Laya could not read the complete input", "calls": [{"model": "m", "ok": False}]}}
    post_returning(monkeypatch, lambda url: httpx.Response(413, json=detail, request=httpx.Request("POST", url)), [])
    with pytest.raises(LayaServiceError, match="complete input") as error:
        LAYAModel("http://laya:9120").ask("auto", "t", QUESTIONS, 512)
    assert error.value.calls == [{"model": "m", "ok": False}]


def test_a_service_that_cannot_be_reached_is_a_runtime_error(monkeypatch):
    def post(url, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(laya_model.httpx, "post", post)
    with pytest.raises(RuntimeError, match="could not be reached"):
        LAYAModel("http://laya:9120").ask("auto", "t", QUESTIONS, 512)


def test_without_a_url_nothing_is_configured(monkeypatch):
    monkeypatch.delenv("LAYA_SERVICE_URL", raising=False)
    assert laya_model.configured() is False
    with pytest.raises(LayaServiceError, match="LAYA_SERVICE_URL"):
        laya_model.agent().ask("auto", "t", QUESTIONS, 512)
    monkeypatch.setenv("LAYA_SERVICE_URL", "http://laya:9120")
    assert laya_model.configured() is True


def test_strategies_lists_the_service_names_and_its_default(monkeypatch):
    seen = {}

    def get(url, headers=None, timeout=None):
        seen.update(url=url, headers=headers)
        return httpx.Response(200, json={"default": "auto", "strategies": ["english-only", "auto"]})

    monkeypatch.setattr(httpx, "get", get)
    result = LAYAModel("http://laya:9120/", token="t").strategies()
    assert result == {"strategies": ["english-only", "auto"], "default": "auto"}
    assert seen == {"url": "http://laya:9120/v1/strategies", "headers": {"X-Internal-Token": "t"}}


def test_strategies_accepts_a_mapping_of_names(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200, json={"default": "auto", "strategies": {"a": "x", "b": "y"}}))
    assert LAYAModel("http://laya:9120").strategies()["strategies"] == ["a", "b"]


def test_strategies_errors_become_service_errors(monkeypatch):
    with pytest.raises(LayaServiceError, match="not configured"):
        LAYAModel("").strategies()
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(500, text="boom"))
    with pytest.raises(LayaServiceError) as refused:
        LAYAModel("http://laya:9120").strategies()
    assert refused.value.status == 500

    def down(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx, "get", down)
    with pytest.raises(LayaServiceError, match="could not be reached"):
        LAYAModel("http://laya:9120").strategies()
