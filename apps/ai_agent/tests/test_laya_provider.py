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
    monkeypatch.setattr(laya_provider, "_questions", laya_provider.LayaQuestions(fake))
    return fake


def ask(request=REQUEST, **kwargs):
    question = request if isinstance(request, str) else json.dumps(request)
    return asyncio.run(laya_provider.run_chat(question, [], None, [], **kwargs))


def payload(result):
    return json.loads(result.response)


def request_with(**changes):
    data = copy.deepcopy(REQUEST)
    data.update(changes)
    return data


def question(**changes):
    return {"type": "choice", "instructions": "Pick", "criteria": {"a": "A", "b": "B"}, **changes}


def test_answers_every_question_type_and_reports_token_usage(engine):
    result = ask()
    assert payload(result) == {
        "answers": {
            "category": {"type": "choice", "choice": "database",
                         "probabilities": {"database": 0.9, "network": 0.1},
                         "answer_confidence": 0.9, "uncertain": False},
            "severity": {"type": "score", "score": 1.4,
                         "legend": {"0": "none", "1": "minor", "2": "major"},
                         "answer_confidence": 0.9, "uncertain": False},
            "problem": {"type": "noul", "noul": 0.95, "answer_confidence": 0.9, "uncertain": False},
        },
        "uncertain": False,
    }
    assert result.provider_id == "laya"
    assert result.model == "convaiinnovations/laya"
    assert result.input_tokens == result.total_tokens == 120
    assert result.output_tokens == 0
    assert result.tools_used == result.tool_calls == []


def test_engine_gets_the_text_and_only_the_known_question_fields(engine):
    ask()
    state, questions, kwargs = engine.calls[0]
    assert state == "SQLite database is locked"
    assert questions == REQUEST["questions"]
    assert "criteria" not in questions["problem"]
    assert kwargs["max_len"] == 512


def test_low_confidence_marks_that_answer_and_the_whole_result_uncertain(engine):
    engine.result = prediction(confidence=0.4)
    data = payload(ask())
    assert data["uncertain"] is True
    assert all(answer["uncertain"] for answer in data["answers"].values())
    assert data["answers"]["category"]["choice"] == "database"


def test_min_confidence_can_be_set_per_request(engine):
    assert payload(ask(request_with(min_confidence=0.95)))["uncertain"] is True
    engine.result = prediction(confidence=0.6)
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
        ask()


def test_dropped_state_tokens_return_no_answers(engine):
    engine.result["usage"]["state_tokens_dropped"] = 3
    with pytest.raises(ValueError, match="complete input"):
        ask()


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
        ask()


@pytest.mark.parametrize("usage", [None, []])
def test_a_non_dict_usage_is_rejected(engine, usage):
    engine.result["usage"] = usage
    with pytest.raises(ValueError, match="Laya returned"):
        ask()


def test_a_missing_answer_is_rejected(engine):
    del engine.result["answers"]["problem"]
    with pytest.raises(ValueError, match="Laya returned"):
        ask()


def test_inference_errors_propagate_without_a_fallback(engine):
    engine.error = RuntimeError("local model failed")
    with pytest.raises(RuntimeError, match="local model failed"):
        ask()
    assert len(engine.calls) == 1


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


# --- Jev as the remote fallback (llm/jev_classifier.py) ---------------------------------------------

from src.llm import jev_classifier  # noqa: E402


def jev_on(monkeypatch, picks, max_input_chars=16_000):
    """Switch the fallback on; `picks` maps a question's instructions to a Choice or an error."""
    config = jev_classifier.ClassifierSettings(triage_fallback=True, max_input_chars=max_input_chars)
    monkeypatch.setattr(jev_classifier, "settings", lambda: config)
    monkeypatch.setattr(jev_classifier, "available", lambda: True)
    asked = []

    def ask_choice(subject, criteria, timeout=None):
        asked.append((subject, dict(criteria)))
        outcome = next(v for k, v in picks.items() if k in subject)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(jev_classifier, "ask_choice", ask_choice)
    return asked


def test_jev_is_not_asked_unless_the_fallback_is_on(engine, monkeypatch):
    engine.result = prediction(confidence=0.2)
    monkeypatch.setattr(jev_classifier, "ask_choice", lambda *a, **k: pytest.fail("Jev must not be called"))

    result = payload(ask())

    assert result["uncertain"] is True and "answered_by" not in json.dumps(result)


def test_an_uncertain_choice_goes_to_jev_and_a_sure_one_stays_with_laya(engine, monkeypatch):
    low = prediction()
    low["answers"]["category"]["answer_confidence"] = 0.3
    engine.result = low
    asked = jev_on(monkeypatch, {"Which category?": jev_classifier.Choice("network", 90, 50)})

    result = ask()
    answers = payload(result)["answers"]

    assert len(asked) == 1 and asked[0][1] == {"database": "SQL and storage", "network": "Connections"}
    assert answers["category"]["choice"] == "network" and answers["category"]["answered_by"] == "jev"
    assert answers["category"]["probabilities"] == {"database": 0.1, "network": 0.9}
    assert answers["category"]["uncertain"] is False
    assert "answered_by" not in answers["severity"] and answers["severity"]["score"] == 1.4
    assert payload(result)["uncertain"] is False
    assert result.input_tokens == 120 + 50 and "answered 1 question" in result.model_note


def test_a_jev_answer_below_the_threshold_is_still_marked_uncertain(engine, monkeypatch):
    engine.result = prediction(confidence=0.2)
    jev_on(monkeypatch, {
        "Which category?": jev_classifier.Choice("network", 60, 10),
        "How severe?": jev_classifier.Choice("2", 95, 10),
        "Is there a problem?": jev_classifier.Choice("false", 90, 10),
    })

    answers = payload(ask())["answers"]

    assert answers["category"]["uncertain"] is True
    assert answers["severity"]["score"] == 2.0 and answers["severity"]["legend"]["0"] == "none"
    assert answers["problem"]["noul"] == pytest.approx(0.1) and answers["problem"]["uncertain"] is False


def test_score_and_noul_questions_are_sent_to_jev_as_named_options(engine, monkeypatch):
    engine.result = prediction(confidence=0.2)
    asked = jev_on(monkeypatch, {
        "Which category?": jev_classifier.Choice("network", 90, 1),
        "How severe?": jev_classifier.Choice("1", 90, 1),
        "Is there a problem?": jev_classifier.Choice("true", 80, 1),
    })

    result = payload(ask())

    options = {question: criteria for (question, criteria) in asked}
    severity = next(c for q, c in options.items() if "How severe?" in q)
    problem = next(c for q, c in options.items() if "Is there a problem?" in q)
    assert severity == {"0": "level 0: none", "1": "level 1: minor", "2": "level 2: major"}
    assert set(problem) == {"false", "true"}
    assert result["answers"]["problem"]["noul"] == 0.8


def test_a_failing_jev_leaves_layas_unsure_answer_as_it_was(engine, monkeypatch):
    engine.result = prediction(confidence=0.2)
    jev_on(monkeypatch, {"?": jev_classifier.ClassifierError("down")})

    result = ask()
    data = payload(result)

    assert data["uncertain"] is True and "answered_by" not in json.dumps(data)
    assert result.input_tokens == 120 and result.model_note == ""


def test_a_text_too_long_for_laya_goes_to_jev_without_asking_laya(engine, monkeypatch):
    asked = jev_on(monkeypatch, {
        "Which category?": jev_classifier.Choice("database", 90, 30),
        "How severe?": jev_classifier.Choice("2", 90, 30),
        "Is there a problem?": jev_classifier.Choice("true", 90, 30),
    })
    long_text = "x " * 3000

    result = ask(request_with(text=long_text))

    assert engine.calls == [] and len(asked) == 3
    assert {a["answered_by"] for a in payload(result)["answers"].values()} == {"jev"}
    assert result.input_tokens == 90


def test_input_laya_cannot_read_in_full_goes_to_jev(engine, monkeypatch):
    engine.result = prediction()
    engine.result["usage"]["truncated"] = True
    jev_on(monkeypatch, {
        "Which category?": jev_classifier.Choice("database", 90, 5),
        "How severe?": jev_classifier.Choice("1", 90, 5),
        "Is there a problem?": jev_classifier.Choice("true", 90, 5),
    })

    answers = payload(ask())["answers"]

    assert set(answers) == {"category", "severity", "problem"}
    assert all(a["answered_by"] == "jev" for a in answers.values())


def test_unreadable_input_with_a_failing_jev_returns_no_answers(engine, monkeypatch):
    engine.result = prediction()
    engine.result["usage"]["truncated"] = True
    jev_on(monkeypatch, {"?": jev_classifier.ClassifierError("the gateway answered HTTP 500")})

    with pytest.raises(ValueError, match="could not read the complete input.*Jev could not answer either.*HTTP 500"):
        ask()


def test_unreadable_input_with_jev_unavailable_keeps_the_old_message(engine, monkeypatch):
    engine.result = prediction()
    engine.result["usage"]["truncated"] = True
    monkeypatch.setattr(jev_classifier, "available", lambda: False)

    with pytest.raises(ValueError, match="could not read the complete input"):
        ask()


def test_a_text_over_the_jev_limit_is_refused_before_anything_runs(engine, monkeypatch):
    jev_on(monkeypatch, {}, max_input_chars=100)

    with pytest.raises(ValueError, match="at most 100 characters"):
        ask(request_with(text="x" * 101))
    assert engine.calls == []
