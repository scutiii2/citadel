"""The `jev` backend: TypeSafe's own /v1/systemone API."""

from __future__ import annotations

import json

import pytest

from src.providers.decision import decision, typesafe_classifier
from src.providers.decision.decision import ClassifierError

CRITERIA = {"database": "SQL and storage", "network": "Connections"}


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    decision.reset_cache()
    monkeypatch.setattr(decision, "read_section", lambda path, name, default=None: {})
    yield
    decision.reset_cache()


def reply(choice="network", confidence=0.8, tokens=428):
    return {
        "model": "jev-1.13.0",
        "answers": {"answer": {
            "type": "choice", "choice": choice, "confidence": confidence,
            "probabilities": {"network": 0.9, "database": 0.1},
        }},
        "usage": {"input_tokens": tokens, "output_tokens": 73},
    }


def test_available_follows_the_key(monkeypatch):
    monkeypatch.delenv(typesafe_classifier.KEY_ENV, raising=False)
    assert typesafe_classifier.available() is False
    monkeypatch.setenv(typesafe_classifier.KEY_ENV, " k ")
    assert typesafe_classifier.available() is True


def test_asking_without_a_key_is_a_classifier_error(monkeypatch):
    monkeypatch.delenv(typesafe_classifier.KEY_ENV, raising=False)
    with pytest.raises(ClassifierError, match="TYPESAFE_API_KEY"):
        typesafe_classifier.ask_choice("text", CRITERIA, "Which?", 3.0)


def test_one_choice_question_is_sent_and_confidence_becomes_a_percentage(monkeypatch):
    monkeypatch.setenv(typesafe_classifier.KEY_ENV, "secret")
    sent = {}

    def post(url, payload, key, timeout):
        sent.update(url=url, payload=payload, key=key, timeout=timeout)
        return reply(confidence=0.835)

    monkeypatch.setattr(typesafe_classifier, "_post", post)

    picked = typesafe_classifier.ask_choice("connection reset", CRITERIA, "Which area?", 2.5)

    assert picked == decision.Choice("network", 84, 428, "jev", "jev-1.13.0", {"network": 0.9, "database": 0.1})
    assert sent["url"] == "https://api.typesafe.ai/v1/systemone" and sent["key"] == "secret" and sent["timeout"] == 2.5
    assert sent["payload"] == {
        "state": "connection reset", "model": "jev-latest",
        "questions": {"answer": {"type": "choice", "instructions": "Which area?", "criteria": CRITERIA}},
    }
    json.dumps(sent["payload"])


def test_the_url_and_model_come_from_the_typesafe_section(monkeypatch):
    monkeypatch.setattr(decision, "read_section", lambda *a, **k: {"typesafe": {"model": "jev-preview"}})
    decision.reset_cache()
    assert typesafe_classifier._payload(decision.settings().typesafe.model, "t", CRITERIA, "q")["model"] == "jev-preview"


@pytest.mark.parametrize("body", [
    {}, {"answers": {}}, {"answers": {"answer": {"choice": "network"}}},
    reply(choice="other"), reply(confidence=1.5), reply(confidence="high"), reply(confidence=True),
])
def test_an_unusable_answer_is_a_classifier_error(body):
    with pytest.raises(ClassifierError):
        typesafe_classifier._parse(body, CRITERIA)


def test_a_missing_or_odd_token_count_reads_as_zero():
    body = reply()
    del body["usage"]
    assert typesafe_classifier._parse(body, CRITERIA).prompt_tokens == 0
    body["usage"] = {"input_tokens": -3}
    assert typesafe_classifier._parse(body, CRITERIA).prompt_tokens == 0


def test_the_apis_probabilities_are_kept_when_they_cover_the_options():
    picked = typesafe_classifier._parse(reply(), CRITERIA)
    assert picked.probabilities == {"database": 0.1, "network": 0.9}


@pytest.mark.parametrize("probabilities", [
    None, {}, {"network": 1.0}, {"network": 0.9, "database": 0.1, "other": 0.0},
    {"network": 0.9, "database": 1.4}, {"network": 0.9, "database": "x"}, {"network": True, "database": 0.1},
])
def test_probabilities_that_do_not_fit_are_dropped(probabilities):
    body = reply()
    body["answers"]["answer"]["probabilities"] = probabilities
    assert typesafe_classifier._parse(body, CRITERIA).probabilities is None
