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


# --- Jev as the remote fallback (llm/decision.py) ---------------------------------------------

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


def test_jev_is_not_asked_unless_the_fallback_is_on(engine, monkeypatch):
    engine.result = prediction(confidence=0.2)
    monkeypatch.setattr(decision, "ask_choice", lambda *a, **k: pytest.fail("Jev must not be called"))

    result = payload(ask())

    assert result["uncertain"] is True and "answered_by" not in json.dumps(result)


def test_an_uncertain_choice_is_weighed_with_jevs_and_a_sure_one_stays_with_laya(engine, monkeypatch):
    low = prediction()
    low["answers"]["category"]["answer_confidence"] = 0.5
    engine.result = low
    asked = jev_on(monkeypatch, {"Which category?": decision.Choice("network", 60, 50, "jev")})

    result = ask()
    answers = payload(result)["answers"]

    assert len(asked) == 1 and asked[0][1] == {"database": "SQL and storage", "network": "Connections"}
    # Laya said database (0.9 / 0.1 at 0.5), Jev network (0.4 / 0.6 at 0.6): close confidences and two options, so the
    # pair rule weighs them: 0.45/0.05 against 0.24/0.36 gives differences 0.21 and 0.31, too close to call.
    category = answers["category"]
    assert category["answered_by"] == "laya+jev" and category["resolved_by"] == "pair"
    assert category["choice"] == "network" and category["candidates"] == ["database", "network"]
    assert category["probabilities"] == {"database": 0.4038, "network": 0.5962}
    assert category["answer_confidence"] == 0.5962 and category["uncertain"] is True
    assert category["disagreement"] == {"laya": "database", "jev": "network"}
    assert "answered_by" not in answers["severity"] and answers["severity"]["score"] == 1.4
    assert payload(result)["uncertain"] is True
    assert result.input_tokens == 120 + 50 and "reviewed 1 question" in result.model_note


def test_a_jev_answer_below_the_threshold_is_still_marked_uncertain(engine, monkeypatch):
    engine.result = prediction(confidence=0.2)
    jev_on(monkeypatch, {
        "Which category?": decision.Choice("network", 60, 10, "jev"),
        "How severe?": decision.Choice("2", 95, 10, "jev"),
        "Is there a problem?": decision.Choice("false", 90, 10, "jev"),
    })

    answers = payload(ask())["answers"]

    assert answers["category"]["uncertain"] is True
    assert answers["severity"]["score"] == 2.0 and answers["severity"]["legend"]["0"] == "none"
    assert answers["problem"]["noul"] == pytest.approx(0.1) and answers["problem"]["uncertain"] is False


def test_score_and_noul_questions_are_sent_to_jev_as_named_options(engine, monkeypatch):
    engine.result = prediction(confidence=0.2)
    asked = jev_on(monkeypatch, {
        "Which category?": decision.Choice("network", 90, 1, "jev"),
        "How severe?": decision.Choice("1", 90, 1, "jev"),
        "Is there a problem?": decision.Choice("true", 80, 1, "jev"),
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
    jev_on(monkeypatch, {"?": decision.ClassifierError("down")})

    result = ask()
    data = payload(result)

    assert data["uncertain"] is True and "answered_by" not in json.dumps(data)
    assert result.input_tokens == 120 and result.model_note == ""


def test_a_text_too_long_for_laya_goes_to_jev_without_asking_laya(engine, monkeypatch):
    asked = jev_on(monkeypatch, {
        "Which category?": decision.Choice("database", 90, 30, "jev"),
        "How severe?": decision.Choice("2", 90, 30, "jev"),
        "Is there a problem?": decision.Choice("true", 90, 30, "jev"),
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
        "Which category?": decision.Choice("database", 90, 5, "jev"),
        "How severe?": decision.Choice("1", 90, 5, "jev"),
        "Is there a problem?": decision.Choice("true", 90, 5, "jev"),
    })

    answers = payload(ask())["answers"]

    assert set(answers) == {"category", "severity", "problem"}
    assert all(a["answered_by"] == "jev" for a in answers.values())


def test_unreadable_input_with_a_failing_jev_returns_no_answers(engine, monkeypatch):
    engine.result = prediction()
    engine.result["usage"]["truncated"] = True
    jev_on(monkeypatch, {"?": decision.ClassifierError("the gateway answered HTTP 500")})

    with pytest.raises(ValueError, match="could not read the complete input.*The fallback classifier could not answer either.*HTTP 500"):
        ask()


def test_unreadable_input_with_jev_unavailable_keeps_the_old_message(engine, monkeypatch):
    engine.result = prediction()
    engine.result["usage"]["truncated"] = True
    monkeypatch.setattr(decision, "available", lambda *a, **k: False)

    with pytest.raises(ValueError, match="could not read the complete input"):
        ask()


def test_a_text_over_the_jev_limit_is_refused_before_anything_runs(engine, monkeypatch):
    jev_on(monkeypatch, {}, max_input_chars=100)

    with pytest.raises(ValueError, match="at most 100 characters"):
        ask(request_with(text="x" * 101))
    assert engine.calls == []


def test_a_backends_real_probabilities_are_weighed_against_layas(engine, monkeypatch):
    engine.result = prediction(confidence=0.5)
    jev_on(monkeypatch, {
        "Which category?": decision.Choice("network", 70, 10, "jev", "", {"database": 0.3, "network": 0.7}),
        "How severe?": decision.Choice("1", 90, 10, "jev"),
        "Is there a problem?": decision.Choice("true", 90, 10, "jev"),
    })

    category = payload(ask())["answers"]["category"]

    # 0.45/0.05 against 0.21/0.49: differences 0.24 and 0.44, so a real tie-break is not met.
    assert category["probabilities"] == {"database": 0.3529, "network": 0.6471} and category["choice"] == "network"
    assert category["answer_confidence"] == 0.6471 and category["uncertain"] is True and category["candidates"]


def test_a_distribution_that_misses_an_option_is_replaced_by_the_even_split_before_weighing(engine, monkeypatch):
    engine.result = prediction(confidence=0.6)
    jev_on(monkeypatch, {
        "Which category?": decision.Choice("network", 80, 10, "jev", "", {"network": 0.8}),
        "How severe?": decision.Choice("1", 90, 10, "jev"),
        "Is there a problem?": decision.Choice("true", 90, 10, "jev"),
    })

    # Jev's 0.8 on network is spread as 0.2 / 0.8; weighed: 0.54/0.06 against 0.16/0.64, differences 0.38 and 0.58.
    assert payload(ask())["answers"]["category"]["probabilities"] == {"database": 0.3958, "network": 0.6042}


def test_two_answers_that_agree_keep_the_higher_confidence(engine, monkeypatch):
    low = prediction()
    low["answers"]["category"]["answer_confidence"] = 0.6
    engine.result = low
    jev_on(monkeypatch, {"Which category?": decision.Choice("database", 65, 10, "jev", "", {"database": 0.8, "network": 0.2})})

    category = payload(ask())["answers"]["category"]

    assert category["choice"] == "database" and category["answer_confidence"] == 0.65
    assert category["probabilities"] == {"database": 0.85, "network": 0.15}
    assert "disagreement" not in category and category["uncertain"] is True  # 0.65 is still under the 0.7 gate


# --- narrowing: drop the options both answers rank far below the rest, then ask again -------------

AREA = {
    "text": "The checkout page times out for about half of users since this morning.",
    "questions": {"area": {"type": "choice", "instructions": "Which area is affected",
                           "criteria": {"billing": "payments", "frontend": "web UI", "network": "connections"}}},
}


def area_prediction(probabilities, confidence, tokens=120):
    choice = max(probabilities, key=probabilities.get)
    return {
        "answers": {"area": {"choice": choice, "probabilities": probabilities, "answer_confidence": confidence}},
        "usage": {"input_tokens": tokens, "output_tokens": 0, "state_tokens": 12, "truncated": False},
    }


class ScriptedEngine:
    """Laya answers from a list, one per call; an exception in the list is raised."""

    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def predict(self, state, questions, **kwargs):
        self.calls.append(copy.deepcopy(questions))
        outcome = self.results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def scripted(monkeypatch, engine, *fallback, prune_ratio=0.25):
    """Laya runs `engine`; the fallback answers from `fallback` in order and the options it was asked are recorded."""
    monkeypatch.setattr(laya_provider, "_questions", laya_provider.LayaQuestions(engine))
    config = decision.ClassifierSettings(triage_fallback=True, triage_prune_ratio=prune_ratio)
    monkeypatch.setattr(decision, "settings", lambda: config)
    monkeypatch.setattr(decision, "available", lambda *a, **k: True)
    queue, asked = list(fallback), []

    def ask_choice(subject, criteria, question, feature, **kwargs):
        asked.append(list(criteria))
        outcome = queue.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(decision, "ask_choice", ask_choice)
    return asked


JEV_FIRST = decision.Choice("billing", 56, 10, "jev", "", {"billing": 0.71, "frontend": 0.26, "network": 0.03})
LAYA_FIRST = area_prediction({"billing": 0.24, "frontend": 0.66, "network": 0.10}, 0.55)


def area():
    return payload(ask(AREA))["answers"]["area"]


def test_an_option_far_below_the_rest_is_dropped_and_laya_decides_the_narrowed_question(monkeypatch):
    laya = ScriptedEngine(LAYA_FIRST, area_prediction({"billing": 0.2, "frontend": 0.8}, 0.9, tokens=60))
    asked = scripted(monkeypatch, laya, JEV_FIRST)

    result = ask(AREA)
    answer = payload(result)["answers"]["area"]

    assert list(laya.calls[1]["area"]["criteria"]) == ["billing", "frontend"]
    assert asked == [["billing", "frontend", "network"]]  # the fallback was not needed again
    assert answer["choice"] == "frontend" and answer["answered_by"] == "laya" and answer["eliminated"] == ["network"]
    assert answer["probabilities"] == {"billing": 0.2, "frontend": 0.8, "network": 0.0}
    assert answer["uncertain"] is False
    assert result.input_tokens == 120 + 10 + 60


def test_an_unsure_laya_hands_the_narrowed_question_to_the_fallback(monkeypatch):
    laya = ScriptedEngine(LAYA_FIRST, area_prediction({"billing": 0.45, "frontend": 0.55}, 0.4, tokens=60))
    second = decision.Choice("frontend", 80, 7, "jev", "", {"billing": 0.1, "frontend": 0.9})
    asked = scripted(monkeypatch, laya, JEV_FIRST, second)

    result = ask(AREA)
    answer = payload(result)["answers"]["area"]

    assert asked == [["billing", "frontend", "network"], ["billing", "frontend"]]
    assert answer["choice"] == "frontend" and answer["answered_by"] == "jev" and answer["eliminated"] == ["network"]
    assert answer["probabilities"] == {"billing": 0.1, "frontend": 0.9, "network": 0.0}
    assert result.input_tokens == 120 + 10 + 60 + 7


def test_when_the_fallback_fails_the_second_time_layas_narrowed_answer_stands(monkeypatch):
    laya = ScriptedEngine(LAYA_FIRST, area_prediction({"billing": 0.45, "frontend": 0.55}, 0.4, tokens=60))
    scripted(monkeypatch, laya, JEV_FIRST, decision.ClassifierError("down"))

    answer = area()

    assert answer["choice"] == "frontend" and answer["answered_by"] == "laya" and answer["uncertain"] is True
    assert answer["eliminated"] == ["network"]


def test_when_laya_cannot_take_the_narrowed_question_the_fallbacks_answer_stands(monkeypatch):
    scripted(monkeypatch, ScriptedEngine(LAYA_FIRST, RuntimeError("gone")), JEV_FIRST)

    answer = area()

    assert answer["choice"] == "billing" and answer["answered_by"] == "jev" and "eliminated" not in answer


def test_nothing_is_dropped_when_no_option_is_far_below_the_rest(monkeypatch):
    laya = ScriptedEngine(area_prediction({"billing": 0.3, "frontend": 0.4, "network": 0.3}, 0.5))
    asked = scripted(monkeypatch, laya, decision.Choice("frontend", 50, 5, "jev", "", {"billing": 0.3, "frontend": 0.4, "network": 0.3}))

    answer = area()

    assert len(laya.calls) == 1 and len(asked) == 1
    assert answer["answered_by"] == "laya+jev" and answer["choice"] == "frontend" and "eliminated" not in answer


def test_a_prune_ratio_of_zero_never_drops_an_option(monkeypatch):
    laya = ScriptedEngine(LAYA_FIRST)
    scripted(monkeypatch, laya, JEV_FIRST, prune_ratio=0)

    answer = area()

    assert len(laya.calls) == 1 and answer["answered_by"] == "laya+jev" and "eliminated" not in answer


def test_at_least_two_options_always_stay(monkeypatch):
    laya = ScriptedEngine(
        area_prediction({"billing": 0.8, "frontend": 0.1, "network": 0.1}, 0.5),
        area_prediction({"billing": 0.9, "frontend": 0.1}, 0.9, tokens=60),
    )
    scripted(monkeypatch, laya, decision.Choice("billing", 60, 5, "jev", "", {"billing": 0.9, "frontend": 0.05, "network": 0.05}))

    area()

    assert list(laya.calls[1]["area"]["criteria"]) == ["billing", "frontend"]  # the first of two tied options stays


def test_a_text_laya_could_not_read_is_not_narrowed_or_blended(monkeypatch):
    laya = ScriptedEngine()
    asked = scripted(monkeypatch, laya, JEV_FIRST)

    answer = payload(ask({**AREA, "text": "x " * 3000}))["answers"]["area"]

    assert laya.calls == [] and asked == [["billing", "frontend", "network"]]
    assert answer["answered_by"] == "jev" and "eliminated" not in answer and "disagreement" not in answer


# --- the rounds trace ------------------------------------------------------------------------------

def test_a_narrowed_answer_lists_every_round_in_order(monkeypatch):
    laya = ScriptedEngine(LAYA_FIRST, area_prediction({"billing": 0.45, "frontend": 0.55}, 0.4, tokens=60))
    second = decision.Choice("billing", 36, 7, "jev", "", {"billing": 0.68, "frontend": 0.32})
    scripted(monkeypatch, laya, JEV_FIRST, second)

    rounds = area()["rounds"]

    assert [r["step"] for r in rounds] == [
        "laya", "jev", "average", "laya", "jev", "laya x confidence", "jev x confidence", "difference",
    ]
    assert rounds[0] == {
        "step": "laya", "choice": "frontend", "probabilities": {"billing": 0.24, "frontend": 0.66, "network": 0.1}, "confidence": 0.55,
    }
    assert rounds[1]["choice"] == "billing" and rounds[1]["confidence"] == 0.56
    assert rounds[2] == {
        "step": "average", "probabilities": {"billing": 0.475, "frontend": 0.46, "network": 0.065}, "eliminated": ["network"],
    }
    assert rounds[3]["options"] == ["billing", "frontend"] and rounds[3]["confidence"] == 0.4
    assert rounds[4] == {
        "step": "jev", "choice": "billing", "probabilities": {"billing": 0.68, "frontend": 0.32}, "confidence": 0.36,
        "options": ["billing", "frontend"],
    }


def test_a_sure_narrowed_laya_ends_the_trace_there(monkeypatch):
    laya = ScriptedEngine(LAYA_FIRST, area_prediction({"billing": 0.2, "frontend": 0.8}, 0.9, tokens=60))
    scripted(monkeypatch, laya, JEV_FIRST)

    assert [r["step"] for r in area()["rounds"]] == ["laya", "jev", "average", "laya"]


def test_a_blended_answer_traces_both_answers_and_their_average(monkeypatch):
    laya = ScriptedEngine(area_prediction({"billing": 0.3, "frontend": 0.4, "network": 0.3}, 0.5))
    scripted(monkeypatch, laya, decision.Choice("frontend", 50, 5, "jev", "", {"billing": 0.3, "frontend": 0.4, "network": 0.3}))

    rounds = area()["rounds"]

    assert [r["step"] for r in rounds] == ["laya", "jev", "average"] and "eliminated" not in rounds[2]


def test_the_trace_records_a_laya_that_could_not_take_the_narrowed_question(monkeypatch):
    scripted(monkeypatch, ScriptedEngine(LAYA_FIRST, RuntimeError("gone")), JEV_FIRST)

    answer = area()

    assert answer["choice"] == "billing" and answer["rounds"][-1] == {"step": "laya", "options": ["billing", "frontend"], "failed": "gone"}


def test_an_answer_without_a_second_opinion_has_no_trace(engine):
    engine.result = prediction(confidence=0.2)
    assert "rounds" not in payload(ask())["answers"]["category"]


# --- the confidence gap: a much more confident model decides alone -----------------------------

def test_a_much_more_confident_fallback_decides_the_question_alone(engine, monkeypatch):
    low = prediction()
    low["answers"]["category"]["answer_confidence"] = 0.3
    engine.result = low
    jev_on(monkeypatch, {"Which category?": decision.Choice("network", 90, 50, "jev")})

    category = payload(ask())["answers"]["category"]

    assert category["choice"] == "network" and category["answered_by"] == "jev" and category["deferred_to"] == "jev"
    assert category["answer_confidence"] == 0.9 and category["uncertain"] is False
    assert category["probabilities"] == {"database": 0.1, "network": 0.9}  # its own, not averaged
    assert [r["step"] for r in category["rounds"]] == ["laya", "jev", "gap"]
    assert category["rounds"][2] == {"step": "gap", "gap": 0.6, "deferred_to": "jev"}
    assert "eliminated" not in category and "disagreement" not in category


def test_a_much_more_confident_laya_keeps_its_own_answer(engine, monkeypatch):
    unsure = prediction()
    unsure["answers"]["category"]["answer_confidence"] = 0.65
    engine.result = unsure
    jev_on(monkeypatch, {"Which category?": decision.Choice("network", 30, 50, "jev")})

    category = payload(ask())["answers"]["category"]

    assert category["choice"] == "database" and category["answered_by"] == "laya" and category["deferred_to"] == "laya"
    assert category["uncertain"] is True  # 0.65 is still under the 0.7 gate


@pytest.mark.parametrize("fallback_confidence, deferred", [(80, True), (79, False)])
def test_the_gap_is_inclusive_at_the_setting(engine, monkeypatch, fallback_confidence, deferred):
    low = prediction()
    low["answers"]["category"]["answer_confidence"] = 0.5
    engine.result = low
    jev_on(monkeypatch, {"Which category?": decision.Choice("network", fallback_confidence, 5, "jev")})

    category = payload(ask())["answers"]["category"]

    assert ("deferred_to" in category) is deferred
    assert category["answered_by"] == ("jev" if deferred else "laya+jev")


def test_a_wider_gap_setting_keeps_averaging(engine, monkeypatch):
    low = prediction()
    low["answers"]["category"]["answer_confidence"] = 0.3
    engine.result = low
    jev_on(monkeypatch, {"Which category?": decision.Choice("network", 90, 50, "jev")})
    config = decision.ClassifierSettings(triage_fallback=True, triage_confidence_gap=1.0)
    monkeypatch.setattr(decision, "settings", lambda: config)

    assert payload(ask())["answers"]["category"]["answered_by"] == "laya+jev"


def test_the_small_talk_case_is_decided_by_the_certain_fallback_without_a_rerun(monkeypatch):
    flat = {"database": 0.1921, "network": 0.1716, "authentication": 0.2052, "configuration": 0.1344, "unknown": 0.2966}
    laya = ScriptedEngine(area_prediction(flat, 0.2966))
    sure = {"database": 0.0, "network": 0.0, "authentication": 0.0, "configuration": 0.0, "unknown": 1.0}
    asked = scripted(monkeypatch, laya, decision.Choice("unknown", 100, 5, "jev", "", sure))
    request = {"text": "Hello, good morning!", "questions": {"area": {
        "type": "choice", "instructions": "Which category?", "criteria": {name: name for name in flat},
    }}}

    answer = payload(ask(request))["answers"]["area"]

    assert answer["choice"] == "unknown" and answer["answered_by"] == "jev" and answer["answer_confidence"] == 1.0
    assert len(laya.calls) == 1 and len(asked) == 1  # no narrowed rerun for either model
    assert answer["uncertain"] is False


# --- the pair rule: two options left and the models still disagree -------------------------------

def two_option_laya(engine, confidence, probabilities):
    """Laya answers `category` with these probabilities at this confidence; its other answers are sure."""
    result = prediction()
    result["answers"]["category"] = {
        "choice": max(probabilities, key=probabilities.get), "probabilities": probabilities, "answer_confidence": confidence,
    }
    engine.result = result


def test_a_clearly_larger_difference_decides_the_pair(engine, monkeypatch):
    two_option_laya(engine, 0.65, {"database": 0.95, "network": 0.05})
    jev_on(monkeypatch, {"Which category?": decision.Choice("network", 40, 5, "jev", "", {"database": 0.45, "network": 0.55})})

    category = payload(ask())["answers"]["category"]
    steps = {r["step"]: r for r in category["rounds"]}

    # Weighed: Laya 0.6175 / 0.0325, Jev 0.18 / 0.22; differences 0.4375 and 0.1875, and 0.1875 < half of 0.4375.
    assert steps["laya x confidence"]["probabilities"] == {"database": 0.6175, "network": 0.0325}
    assert steps["jev x confidence"]["probabilities"] == {"database": 0.18, "network": 0.22}
    assert steps["difference"]["probabilities"] == {"database": 0.4375, "network": 0.1875}
    assert steps["difference"]["choice"] == "database"
    assert category["choice"] == "database" and category["resolved_by"] == "pair" and category["uncertain"] is False
    assert category["probabilities"] == {"database": 0.7, "network": 0.3} and category["answer_confidence"] == 0.7
    assert "candidates" not in category and category["disagreement"] == {"laya": "database", "jev": "network"}
    assert category["answered_by"] == "laya+jev"


def test_two_similar_differences_leave_both_options_open(engine, monkeypatch):
    two_option_laya(engine, 0.6, {"database": 0.6, "network": 0.4})
    jev_on(monkeypatch, {"Which category?": decision.Choice("network", 60, 5, "jev", "", {"database": 0.4, "network": 0.6})})

    category = payload(ask())["answers"]["category"]

    # 0.36/0.24 against 0.24/0.36: both differences are 0.12.
    assert category["probabilities"] == {"database": 0.5, "network": 0.5}
    assert category["uncertain"] is True and category["candidates"] == ["database", "network"]
    assert category["rounds"][-1]["choice"] == "unsure: database or network"
    assert category["choice"] == "database"  # a tie goes to the pick of the more confident model (equal: Laya)


def test_the_pair_ratio_setting_moves_the_line(engine, monkeypatch):
    two_option_laya(engine, 0.65, {"database": 0.95, "network": 0.05})
    jev_on(monkeypatch, {"Which category?": decision.Choice("network", 40, 5, "jev", "", {"database": 0.45, "network": 0.55})})
    config = decision.ClassifierSettings(triage_fallback=True, triage_pair_ratio=0.3)  # 0.1875 is not under 0.3 x 0.4375
    monkeypatch.setattr(decision, "settings", lambda: config)

    category = payload(ask())["answers"]["category"]

    assert category["uncertain"] is True and category["candidates"] == ["database", "network"]


def test_models_that_agree_on_a_pair_are_still_blended(engine, monkeypatch):
    two_option_laya(engine, 0.6, {"database": 0.8, "network": 0.2})
    jev_on(monkeypatch, {"Which category?": decision.Choice("database", 65, 5, "jev", "", {"database": 0.85, "network": 0.15})})

    category = payload(ask())["answers"]["category"]

    assert category["answered_by"] == "laya+jev" and "resolved_by" not in category and category["choice"] == "database"


def test_the_pair_rule_also_closes_a_narrowed_round_that_still_disagrees(monkeypatch):
    laya = ScriptedEngine(LAYA_FIRST, area_prediction({"billing": 0.45, "frontend": 0.55}, 0.4, tokens=60))
    second = decision.Choice("billing", 36, 7, "jev", "", {"billing": 0.68, "frontend": 0.32})
    scripted(monkeypatch, laya, JEV_FIRST, second)

    answer = area()

    # Weighed: Laya 0.18 / 0.22, Jev 0.2448 / 0.1152; differences 0.0648 and 0.1048: too close to call.
    assert answer["resolved_by"] == "pair" and answer["eliminated"] == ["network"] and answer["answered_by"] == "laya+jev"
    assert answer["candidates"] == ["billing", "frontend"] and answer["uncertain"] is True
    assert answer["choice"] == "frontend" and answer["probabilities"] == {"billing": 0.3821, "frontend": 0.6179, "network": 0.0}


def test_more_than_two_options_left_keeps_the_fallbacks_second_answer(monkeypatch):
    # Five options, no one far below the rest to drop: not a pair, so the earlier blend/narrow rules apply.
    flat = {"a": 0.3, "b": 0.25, "c": 0.2, "d": 0.15, "e": 0.1}
    laya = ScriptedEngine(area_prediction(flat, 0.5))
    scripted(monkeypatch, laya, decision.Choice("b", 55, 5, "jev", "", {"a": 0.2, "b": 0.3, "c": 0.2, "d": 0.2, "e": 0.1}))
    request = {"text": "x", "questions": {"area": {"type": "choice", "instructions": "q", "criteria": {k: k for k in flat}}}}

    answer = payload(ask(request))["answers"]["area"]

    assert "resolved_by" not in answer
