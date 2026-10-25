"""The Laya provider validates caller-supplied typed questions, hands them to the triage flow and never
generates text or calls another model. The flow's rules are tested in test_triage_flow.py."""

import asyncio
import copy
import json

import pytest

from src.llm import laya_agent, laya_provider, triage_flow
from src.llm.base_provider import ChatCancelled
from tests.fake_laya import FakeService, choice, result

REQUEST = {
    "text": "SQLite database is locked",
    "questions": {
        "category": {"type": "choice", "instructions": "Which category?",
                     "criteria": {"database": "SQL and storage", "network": "Connections"}},
        "severity": {"type": "score", "instructions": "How severe?", "criteria": ["none", "minor", "major"]},
        "problem": {"type": "noul", "instructions": "Is there a problem?"},
    },
}


def answers():
    return result(
        ("category", choice("database", 0.95, ("database", "network"), uncertain=False)),
        ("severity", {"type": "score", "score": 1.4, "legend": {"0": "none"}, "answer_confidence": 0.9,
                      "uncertain": False, "answered_by": "laya-english"}),
        ("problem", {"type": "noul", "noul": 0.95, "answer_confidence": 0.9, "uncertain": False, "answered_by": "laya-typed"}),
        tokens=120,
    )


@pytest.fixture
def service(monkeypatch):
    fake = FakeService(answers())
    monkeypatch.setattr(laya_agent, "agent", lambda: fake)
    monkeypatch.setattr(triage_flow.laya_agent, "agent", lambda: fake)
    return fake


def ask(request=REQUEST, **kwargs):
    question = request if isinstance(request, str) else json.dumps(request)
    return asyncio.run(laya_provider.run_chat(question, [], None, [], **kwargs))


def payload(result_):
    return json.loads(result_.response)


def request_with(**changes):
    data = copy.deepcopy(REQUEST)
    data.update(changes)
    return data


def question(**changes):
    return {"type": "choice", "instructions": "Pick", "criteria": {"a": "A", "b": "B"}, **changes}




def test_a_request_is_answered_as_a_chat_result_with_no_generated_tokens(service):
    result_ = ask()
    assert result_.provider_id == "laya" and result_.model == "convaiinnovations/laya"
    # Two strategies, so two service calls: choice and score together, noul (typed only by default) on its own.
    assert result_.input_tokens == 240 and result_.output_tokens == 0 and result_.tools_used == []
    body = payload(result_)
    assert body["uncertain"] is False
    assert body["answers"]["category"]["choice"] == "database" and body["answers"]["severity"]["score"] == 1.4


def test_the_service_gets_the_text_and_only_the_known_question_fields(service):
    ask()
    sent = service.asked
    assert [call["strategy"] for call in sent] == ["english-then-typed", "typed-only"]
    assert sent[0]["text"] == "SQLite database is locked" and set(sent[0]["questions"]) == {"category", "severity"}
    assert set(sent[0]["questions"]["category"]) == {"type", "instructions", "criteria"}
    assert set(sent[1]["questions"]["problem"]) == {"type", "instructions"}


def test_min_confidence_reaches_the_service(service):
    ask(request_with(min_confidence=0.5))
    assert service.asked[0]["min_confidence"] == 0.5


def test_text_after_the_json_object_is_ignored(service):
    # delegation appends attachment references to the question string.
    ask(json.dumps(REQUEST) + "\n\nUploaded PDF file references (original attachment order):\nscan.pdf: [PDFMerger file_id: f1]")
    assert service.asked[0]["text"] == "SQLite database is locked"


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
    request_with(questions=[]),
]


@pytest.mark.parametrize("request_data", BAD_REQUESTS)
def test_invalid_requests_are_rejected_before_the_service_is_asked(service, request_data):
    with pytest.raises(ValueError, match="Invalid Laya request"):
        ask(request_data)
    assert not service.asked


def test_the_question_rules_are_the_services_not_garrisons(monkeypatch):
    service = FakeService(answers(), invalid="question 'category' (choice) criteria must be an object of 2 to 10 option: description strings")
    monkeypatch.setattr(triage_flow.laya_agent, "agent", lambda: service)
    with pytest.raises(ValueError, match="Invalid Laya request: question 'category' .* criteria must be"):
        ask(request_with(questions={"q": question(type="multi")}))
    assert not service.asked


def test_questions_are_still_tried_when_the_service_cannot_be_reached_to_validate_them(monkeypatch):
    class Down(FakeService):
        def validate(self, questions):
            raise laya_agent.LayaServiceError("The Laya service could not be reached: down")

    service = Down(answers())
    monkeypatch.setattr(triage_flow.laya_agent, "agent", lambda: service)
    assert payload(ask())["answers"]["category"]["choice"] == "database"


def test_trace_and_local_only_must_be_true_or_false(service):
    for field in ("trace", "local_only"):
        with pytest.raises(ValueError, match=f"{field} must be true or false"):
            laya_provider.parse_request(json.dumps(request_with(**{field: "yes"})))


def test_cancellation_is_checked_before_and_after_the_service_answers(service, monkeypatch):
    monkeypatch.setattr(laya_provider.cancellation, "is_cancelled", lambda _: True)
    with pytest.raises(ChatCancelled):
        ask(request_id="cancelled")
    assert not service.asked

    checks = iter([False, True])
    monkeypatch.setattr(laya_provider.cancellation, "is_cancelled", lambda _: next(checks))
    with pytest.raises(ChatCancelled):
        ask(request_id="during-inference")
    assert len(service.asked) == 2


def test_history_and_extensions_do_not_change_the_input(service):
    result_ = asyncio.run(laya_provider.run_chat(
        json.dumps(REQUEST), [{"role": "user", "content": "old issue"}], None, ["external-server"], caveman=True,
    ))
    assert service.asked[0]["text"] == "SQLite database is locked" and result_.tools_used == []


def test_interpret_does_not_claim_to_summarize_or_generate_text(service):
    with pytest.raises(ValueError, match="does not support"):
        laya_provider.run_interpret("Summarize this conversation")
    assert not service.asked


def test_other_model_ids_cannot_be_used(service):
    with pytest.raises(ValueError, match="only supports"):
        asyncio.run(laya_provider.run_chat(json.dumps(REQUEST), [], "gpt-x", []))
    assert not service.asked


def test_the_provider_is_available_only_when_the_service_is_configured(monkeypatch):
    monkeypatch.delenv("LAYA_SERVICE_URL", raising=False)
    assert laya_provider.is_available() is False
    monkeypatch.setenv("LAYA_SERVICE_URL", "http://laya:9120")
    assert laya_provider.is_available() is True


STRATEGY_BODY = {"text": "t", "questions": {"q": {"type": "choice", "instructions": "?", "criteria": {"a": "A", "b": "B"}}}}


def test_a_request_may_name_a_strategy():
    request = laya_provider.parse_request(json.dumps({**STRATEGY_BODY, "strategy": " typed-only "}))
    assert request.strategy == "typed-only"
    assert laya_provider.parse_request(json.dumps(STRATEGY_BODY)).strategy is None


@pytest.mark.parametrize("value", ["", "  ", 3, None, ["typed-only"]])
def test_a_bad_strategy_is_refused(value):
    with pytest.raises(ValueError, match="strategy must be a non-empty string"):
        laya_provider.parse_request(json.dumps({**STRATEGY_BODY, "strategy": value}))
