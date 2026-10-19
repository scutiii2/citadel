"""The local Laya provider answers caller-supplied typed questions and never
generates text or calls another model."""

import asyncio
import copy
import json

import pytest

from src.llm import laya_provider
from src.llm.base_provider import ChatCancelled

REQUEST = {
    "text": "SQLite database is locked",
    "questions": {
        "category": {"type": "choice", "instructions": "Which category?",
                     "criteria": {"database": "SQL and storage", "network": "Connections"}},
        "severity": {"type": "score", "instructions": "How severe?", "criteria": ["none", "minor", "major"]},
        "problem": {"type": "noul", "instructions": "Is there a problem?"},
    },
}


def prediction(confidence=0.9):
    return {
        "answers": {
            "category": {"choice": "database", "probabilities": {"database": 0.9, "network": 0.1},
                         "answer_confidence": confidence},
            "severity": {"score": 1.4, "answer_confidence": confidence},
            "problem": {"noul": 0.95, "answer_confidence": confidence},
        },
        "usage": {"input_tokens": 120, "output_tokens": 0, "state_tokens": 12, "truncated": False},
    }


class FakeEngine:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else prediction()
        self.error = error
        self.calls = []

    def predict(self, state, questions, **kwargs):
        self.calls.append((state, questions, kwargs))
        if self.error:
            raise self.error
        return copy.deepcopy(self.result)


@pytest.fixture
def engine(monkeypatch):
    fake = FakeEngine()
    fake.typed = FakeEngine()  # the typed-decisions checkpoint: never the real model
    monkeypatch.setattr(laya_provider, "_questions", laya_provider.LayaQuestions(fake, typed=laya_provider.LayaQuestions(fake.typed)))
    return fake


def ask(request=REQUEST, **kwargs):
    question = request if isinstance(request, str) else json.dumps(request)
    return asyncio.run(laya_provider.run_chat(question, [], None, [], **kwargs))


def english(request=REQUEST):
    """The English model's own validated answers and token count, without the triage flow around them."""
    raw = request if isinstance(request, str) else json.dumps(request)
    return laya_provider._questions._laya_answers(laya_provider.parse_request(raw))


def payload(result):
    return json.loads(result.response)


def request_with(**changes):
    data = copy.deepcopy(REQUEST)
    data.update(changes)
    return data


def question(**changes):
    return {"type": "choice", "instructions": "Pick", "criteria": {"a": "A", "b": "B"}, **changes}


def test_answers_every_question_type_and_reports_token_usage(engine):
    answers, tokens = english()
    assert answers == {
        "category": {"type": "choice", "choice": "database",
                     "probabilities": {"database": 0.9, "network": 0.1},
                     "answer_confidence": 0.9, "uncertain": False},
        "severity": {"type": "score", "score": 1.4,
                     "legend": {"0": "none", "1": "minor", "2": "major"},
                     "answer_confidence": 0.9, "uncertain": False},
        "problem": {"type": "noul", "noul": 0.95, "answer_confidence": 0.9, "uncertain": False},
    }
    assert tokens == 120


def test_a_request_is_answered_as_a_chat_result_with_no_generated_tokens(engine):
    result = ask()
    assert payload(result)["uncertain"] is False and set(payload(result)["answers"]) == {"category", "severity", "problem"}
    assert result.provider_id == "laya"
    assert result.model == "convaiinnovations/laya"
    assert result.output_tokens == 0
    assert result.tools_used == result.tool_calls == []


def test_engine_gets_the_text_and_only_the_known_question_fields(engine):
    english()
    state, questions, kwargs = engine.calls[0]
    assert state == "SQLite database is locked"
    assert questions == REQUEST["questions"]
    assert "criteria" not in questions["problem"]
    assert kwargs["max_len"] == 512


def test_low_confidence_marks_that_answer_and_the_whole_result_uncertain(engine):
    engine.result = prediction(confidence=0.4)
    engine.typed.result = prediction(confidence=0.4)
    data = payload(ask())
    assert data["uncertain"] is True
    assert all(answer["uncertain"] for answer in data["answers"].values())
    assert data["answers"]["category"]["choice"] == "database"


def test_min_confidence_can_be_set_per_request(engine):
    assert payload(ask(request_with(min_confidence=0.95)))["uncertain"] is True
    engine.result = prediction(confidence=0.6)
    engine.typed.result = prediction(confidence=0.6)
    assert payload(ask(request_with(min_confidence=0.5)))["uncertain"] is False


def test_text_after_the_json_object_is_ignored(engine):
    # delegation appends attachment references to the question string.
    ask(json.dumps(REQUEST) + "\n\nUploaded PDF file references (original attachment order):\nscan.pdf: [PDFMerger file_id: f1]")
    assert engine.calls[0][0] == "SQLite database is locked"


BAD_REQUESTS = [
    "not json",
    "[]",
    {"text": "x"},
    request_with(extra=1),
    request_with(text=""),
    request_with(text="   "),
    request_with(text="x" * 4001),
    request_with(min_confidence=0),
    request_with(min_confidence=1.5),
    request_with(min_confidence=True),
    request_with(questions={}),
    request_with(questions={f"q{i}": question() for i in range(9)}),
    request_with(questions={"q": "oops"}),
    request_with(questions={"q": question(type="multi")}),
    request_with(questions={"q": question(instructions="")}),
    request_with(questions={"q": question(extra=1)}),
    request_with(questions={"q": question(criteria={"a": "only one"})}),
    request_with(questions={"q": question(criteria={f"o{i}": "d" for i in range(11)})}),
    request_with(questions={"q": question(criteria=["a", "b"])}),
    request_with(questions={"q": question(criteria={"a": 1, "b": "B"})}),
    request_with(questions={"q": question(type="score", criteria={"a": "A", "b": "B"})}),
    request_with(questions={"q": question(type="score", criteria=["only"])}),
    request_with(questions={"q": question(type="noul", criteria={"yes": "y", "no": "n"})}),
]


@pytest.mark.parametrize("request_data", BAD_REQUESTS)
def test_invalid_requests_are_rejected_before_inference(engine, request_data):
    with pytest.raises(ValueError, match="Invalid Laya request"):
        ask(request_data)
    assert not engine.calls


def test_truncated_input_returns_no_answers(engine):
    engine.result["usage"]["truncated"] = True
    with pytest.raises(ValueError, match="complete input"):
        english()


def test_dropped_state_tokens_return_no_answers(engine):
    engine.result["usage"]["state_tokens_dropped"] = 3
    with pytest.raises(ValueError, match="complete input"):
        english()


@pytest.mark.parametrize("qid,field,value", [
    ("category", "choice", "invented"),
    ("category", "probabilities", {"database": 0.9}),
    ("category", "answer_confidence", float("nan")),
    ("severity", "score", 5),
    ("severity", "score", float("nan")),
    ("problem", "noul", 2),
    ("problem", "answer_confidence", True),
])
def test_malformed_model_results_are_rejected(engine, qid, field, value):
    engine.result["answers"][qid][field] = value
    with pytest.raises(ValueError, match="Laya returned"):
        english()


@pytest.mark.parametrize("usage", [None, []])
def test_a_non_dict_usage_is_rejected(engine, usage):
    engine.result["usage"] = usage
    with pytest.raises(ValueError, match="Laya returned"):
        english()


def test_a_missing_answer_is_rejected(engine):
    del engine.result["answers"]["problem"]
    with pytest.raises(ValueError, match="Laya returned"):
        english()


def test_inference_errors_propagate_from_a_model(engine):
    engine.error = RuntimeError("local model failed")
    with pytest.raises(RuntimeError, match="local model failed"):
        english()
    assert len(engine.calls) == 1


def test_a_model_that_fails_is_skipped_and_the_other_one_answers(engine):
    engine.error = RuntimeError("local model failed")
    assert payload(ask())["answers"]["category"]["choice"] == "database"


def test_every_model_failing_is_an_error(engine):
    engine.error = engine.typed.error = RuntimeError("local model failed")
    with pytest.raises(ValueError, match="no model could answer"):
        ask()


def test_cancellation_is_checked_before_and_after_inference(engine, monkeypatch):
    monkeypatch.setattr(laya_provider.cancellation, "is_cancelled", lambda _: True)
    with pytest.raises(ChatCancelled):
        ask(request_id="cancelled")
    assert not engine.calls

    checks = iter([False, True])
    monkeypatch.setattr(laya_provider.cancellation, "is_cancelled", lambda _: next(checks))
    with pytest.raises(ChatCancelled):
        ask(request_id="during-inference")
    assert len(engine.calls) == 1


def test_history_and_extensions_do_not_change_the_input(engine):
    result = asyncio.run(laya_provider.run_chat(
        json.dumps(REQUEST), [{"role": "user", "content": "old issue"}], None,
        ["external-server"], caveman=True,
    ))
    assert engine.calls[0][0] == "SQLite database is locked"
    assert result.tools_used == []


def test_interpret_does_not_claim_to_summarize_or_generate_text(engine):
    with pytest.raises(ValueError, match="does not support"):
        laya_provider.run_interpret("Summarize this conversation")
    assert not engine.calls


def test_other_model_ids_cannot_be_used(engine):
    with pytest.raises(ValueError, match="only supports"):
        asyncio.run(laya_provider.run_chat(json.dumps(REQUEST), [], "gpt-x", []))
    assert not engine.calls


# --- local_only: Laya's own models, never the remote fallback (llm/decision.py) ---------------------------------------------

from src.llm import decision  # noqa: E402


def jev_on(monkeypatch, picks, max_input_chars=16_000):
    """Switch the fallback on; `picks` maps a question's instructions to a Choice or an error."""
    config = decision.ClassifierSettings(triage_fallback=True, max_input_chars=max_input_chars)
    monkeypatch.setattr(decision, "settings", lambda: config)
    monkeypatch.setattr(decision, "available", lambda *a, **k: True)
    asked = []

    def ask_choice(subject, criteria, question, feature, **kwargs):
        asked.append((question, dict(criteria)))
        outcome = next(v for k, v in picks.items() if k in question)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(decision, "ask_choice", ask_choice)
    return asked


def typed_engine(monkeypatch, engine, typed):
    """English is `engine`; the typed-decisions checkpoint is a second fake."""
    monkeypatch.setattr(laya_provider, "_questions", laya_provider.LayaQuestions(engine, typed=laya_provider.LayaQuestions(typed)))


def test_a_local_only_request_asks_the_typed_checkpoint_but_never_jev(engine, monkeypatch):
    engine.result = prediction(confidence=0.2)
    typed = FakeEngine(prediction(confidence=0.99))
    typed_engine(monkeypatch, engine, typed)
    jev_on(monkeypatch, {})
    monkeypatch.setattr(decision, "ask_choice", lambda *a, **k: pytest.fail("Jev must not be called"))

    result = payload(ask(request_with(local_only=True)))

    assert typed.calls and result["uncertain"] is False
    assert result["answers"]["category"]["answered_by"] == "laya-english+laya-typed" and "jev" not in json.dumps(result)


def test_a_local_only_request_stays_uncertain_when_both_laya_models_are_unsure(engine, monkeypatch):
    engine.result = prediction(confidence=0.2)
    typed_engine(monkeypatch, engine, FakeEngine(prediction(confidence=0.2)))
    jev_on(monkeypatch, {})
    monkeypatch.setattr(decision, "ask_choice", lambda *a, **k: pytest.fail("Jev must not be called"))

    result = payload(ask(request_with(local_only=True)))

    assert result["uncertain"] is True and "jev" not in json.dumps(result)


def test_a_local_only_request_does_not_fall_back_for_a_text_laya_cannot_read(engine, monkeypatch):
    engine.result["usage"]["truncated"] = True
    typed = FakeEngine(prediction())
    typed.result["usage"]["truncated"] = True
    typed_engine(monkeypatch, engine, typed)
    jev_on(monkeypatch, {})
    monkeypatch.setattr(decision, "ask_choice", lambda *a, **k: pytest.fail("Jev must not be called"))

    with pytest.raises(ValueError):
        ask(request_with(local_only=True))


def test_local_only_must_be_true_or_false(engine):
    with pytest.raises(ValueError, match="local_only must be true or false"):
        laya_provider.parse_request(json.dumps(request_with(local_only="yes")))
