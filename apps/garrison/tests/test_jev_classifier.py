"""The `jev_vercel` backend: the request it sends through Vercel AI Gateway and how it reads the answer."""

from __future__ import annotations

import json

import pytest

from src.llm import decision, jev_classifier
from src.llm.decision import ClassifierError

CRITERIA = {"database": "SQL and storage", "network": "Connections"}


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    decision.reset_cache()
    monkeypatch.setattr(decision, "read_section", lambda path, name, default=None: {})
    yield
    decision.reset_cache()


def reply(content, tokens=42):
    return {"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": tokens}}


def test_available_follows_the_key(monkeypatch):
    monkeypatch.delenv(jev_classifier.KEY_ENV, raising=False)
    assert jev_classifier.available() is False
    monkeypatch.setenv(jev_classifier.KEY_ENV, "  k  ")
    assert jev_classifier.available() is True


def test_asking_without_a_key_is_a_classifier_error(monkeypatch):
    monkeypatch.delenv(jev_classifier.KEY_ENV, raising=False)
    with pytest.raises(ClassifierError, match="VERCEL_GATEWAY_API_KEY"):
        jev_classifier.ask_choice("text", CRITERIA, "Which?", 3.0)


def test_ask_choice_sends_the_options_and_reads_the_answer(monkeypatch):
    monkeypatch.setenv(jev_classifier.KEY_ENV, "secret")
    sent = {}

    def post(url, payload, key, timeout):
        sent.update(url=url, payload=payload, key=key, timeout=timeout)
        return reply('{"choice": "network", "confidence": 83}')

    monkeypatch.setattr(jev_classifier, "_post", post)

    picked = jev_classifier.ask_choice("connection reset", CRITERIA, "Which area?", 3.0)

    assert picked == decision.Choice("network", 83, 42, "jev_vercel", "typesafe-ai/jev")
    assert sent["key"] == "secret" and sent["timeout"] == 3.0
    assert sent["url"] == "https://ai-gateway.vercel.sh/v1/chat/completions"
    assert sent["payload"]["model"] == "typesafe-ai/jev" and sent["payload"]["temperature"] == 0
    user = sent["payload"]["messages"][1]["content"]
    assert user.startswith("connection reset") and "Question: Which area?" in user
    assert "- database: SQL and storage" in user and "- network: Connections" in user


@pytest.mark.parametrize("content", [
    "not json", '{"choice": "network"}', '{"choice": "other", "confidence": 90}', '{"choice": "network", "confidence": "x"}',
])
def test_an_unusable_answer_is_a_classifier_error(content):
    with pytest.raises(ClassifierError):
        jev_classifier._parse(reply(content), CRITERIA)


def test_a_fenced_answer_and_an_out_of_range_confidence_are_tolerated():
    picked = jev_classifier._parse(reply('```json\n{"choice": "database", "confidence": 250}\n```'), CRITERIA)
    assert (picked.choice, picked.confidence) == ("database", 100)


def test_a_missing_or_odd_token_count_reads_as_zero():
    body = {"choices": [{"message": {"content": '{"choice": "database", "confidence": 70}'}}]}
    assert jev_classifier._parse(body, CRITERIA).prompt_tokens == 0
    body["usage"] = {"prompt_tokens": True}
    assert jev_classifier._parse(body, CRITERIA).prompt_tokens == 0


def test_a_malformed_body_is_a_classifier_error():
    with pytest.raises(ClassifierError, match="unexpected shape"):
        jev_classifier._parse({"choices": []}, CRITERIA)


def test_the_payload_is_json_serialisable():
    json.dumps(jev_classifier._payload("m", "text", CRITERIA, "Which?"))
