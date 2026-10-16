import asyncio

import pytest

from src.opponent.laya_client import LayaChoice, LayaClient, LayaError
from tests.fake_laya import FakeEngine

OPTIONS = {"a": "first move", "b": "second move", "c": "third move"}


def ask(client, **kwargs):
    args = {"text": "Some position.", "instructions": "Which is best?", "options": OPTIONS, **kwargs}
    return asyncio.run(client.choose(**args))


def test_returns_the_chosen_key_and_confidence():
    result = ask(LayaClient(FakeEngine(pick="b", confidence=0.9)))
    assert result == LayaChoice("b", 0.9, False)


def test_low_confidence_is_flagged_uncertain():
    assert ask(LayaClient(FakeEngine(confidence=0.5))).uncertain is True


def test_custom_min_confidence():
    assert ask(LayaClient(FakeEngine(confidence=0.8)), min_confidence=0.9).uncertain is True


def test_question_sent_to_the_engine():
    engine = FakeEngine()
    ask(LayaClient(engine))
    text, questions = engine.calls[0]
    assert text == "Some position."
    assert questions == {"move": {"type": "choice", "instructions": "Which is best?", "criteria": OPTIONS}}


@pytest.mark.parametrize("options", [{"a": "only"}, {chr(97 + i): "x" for i in range(11)}])
def test_option_count_is_checked(options):
    with pytest.raises(LayaError, match="options"):
        ask(LayaClient(FakeEngine()), options=options)


@pytest.mark.parametrize("text", ["", "   ", "x" * 4001])
def test_text_length_is_checked(text):
    with pytest.raises(LayaError, match="characters"):
        ask(LayaClient(FakeEngine()), text=text)


def test_truncated_input_is_rejected():
    with pytest.raises(LayaError, match="complete input"):
        ask(LayaClient(FakeEngine(usage={"truncated": True})))


class BadEngine:
    def __init__(self, result):
        self.result = result

    def predict(self, text, questions, max_len=512):
        return self.result


@pytest.mark.parametrize("result", [
    {},
    {"answers": {"move": {"choice": "z", "probabilities": {"a": 1, "b": 0, "c": 0}, "answer_confidence": 0.9}}},
    {"answers": {"move": {"choice": "a", "probabilities": {"a": 1}, "answer_confidence": 0.9}}},
    {"answers": {"move": {"choice": "a", "probabilities": {"a": 1, "b": 0, "c": 0}, "answer_confidence": 2}}},
    {"answers": {"move": {"choice": "a", "probabilities": {"a": 1, "b": 0, "c": 0}, "answer_confidence": float("nan")}}},
])
def test_invalid_engine_output_is_rejected(result):
    with pytest.raises(LayaError, match="invalid result"):
        ask(LayaClient(BadEngine(result)))


def test_timeout_raises_laya_error():
    with pytest.raises(LayaError, match="timed out"):
        ask(LayaClient(FakeEngine(delay=0.5), timeout=0.05))


def test_missing_package_is_unavailable_and_raises():
    client = LayaClient()
    if client.is_available():
        pytest.skip("laya is installed here")
    with pytest.raises(LayaError, match="optional dependency"):
        ask(client)


def test_injected_engine_counts_as_available():
    assert LayaClient(FakeEngine()).is_available() is True
