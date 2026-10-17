"""scripts/triage_three_way.py: Laya English, Laya typed-decisions and the fallback as three separate voters."""

from __future__ import annotations

import copy
import json

import pytest

from scripts import check_triage_cases as cases
from scripts import triage_three_way as three
from src.llm import decision, laya_provider
from src.llm.laya_provider import LayaQuestions

OPTIONS = {"a": "A", "b": "B", "c": "C"}


def request_json(options=OPTIONS, **extra):
    return json.dumps({"text": "some text", "questions": {"area": {"type": "choice", "instructions": "Which?", "criteria": options}}, **extra})


def prediction(probabilities, confidence, tokens=10):
    choice = max(probabilities, key=probabilities.get)
    return {
        "answers": {"area": {"choice": choice, "probabilities": probabilities, "answer_confidence": confidence}},
        "usage": {"input_tokens": tokens, "output_tokens": 0, "state_tokens": 5, "truncated": False},
    }


class Engine:
    """A Laya checkpoint that answers from a list, one result per call, and records the options it was asked."""

    def __init__(self, *results, error=None):
        self.results, self.error, self.calls = list(results), error, []

    def predict(self, state, questions, **kwargs):
        self.calls.append(list(questions["area"]["criteria"]))
        if self.error:
            raise self.error
        return copy.deepcopy(self.results.pop(0))


def remote(probabilities, confidence):
    return {
        "type": "choice", "choice": max(probabilities, key=probabilities.get), "probabilities": probabilities,
        "answer_confidence": confidence, "uncertain": confidence < 0.7, "answered_by": "jev",
    }


def make(monkeypatch, english, typed, *fallback, use_fallback=True):
    """A ThreeWayTriage over scripted engines; `fallback` are the fallback's answers in order. Returns it with
    the options the fallback was asked about."""
    config = decision.ClassifierSettings(triage_fallback=True)
    monkeypatch.setattr(decision, "settings", lambda: config)
    monkeypatch.setattr(decision, "available", lambda *a, **k: True)
    queue, asked = list(fallback), []

    def ask_fallback(request, qids):
        asked.append(list(request.questions[qids[0]].get("criteria", {})))
        outcome = queue.pop(0)
        return ({qids[0]: outcome} if outcome else {}), 5, []

    monkeypatch.setattr(laya_provider, "_ask_fallback", ask_fallback)
    triage = three.ThreeWayTriage(
        {three.ENGLISH: LayaQuestions(english), three.TYPED: LayaQuestions(typed)}, use_fallback=use_fallback,
    )
    return triage, asked


def run(triage, raw=None):
    result = triage.answer(raw or request_json())
    return json.loads(result.response)["answers"]["area"], result.input_tokens


def steps(answer):
    return [r["step"] for r in answer["rounds"]]


# --- phase 0: the two local models ---------------------------------------------------------------

def test_two_local_models_that_agree_and_are_sure_settle_it_without_the_fallback(monkeypatch):
    english = Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.9))
    typed = Engine(prediction({"a": 0.8, "b": 0.1, "c": 0.1}, 0.8))
    triage, asked = make(monkeypatch, english, typed)

    answer, tokens = run(triage)

    assert answer["choice"] == "a" and answer["answered_by"] == "laya-english+laya-typed" and answer["resolved_by"] == "local"
    assert answer["answer_confidence"] == 0.9 and answer["uncertain"] is False
    assert answer["probabilities"] == {"a": 0.85, "b": 0.075, "c": 0.075}
    assert steps(answer) == ["laya-english", "laya-typed", "average"]
    assert asked == [] and tokens == 20
    assert cases.path_of(answer) == "local"


def test_one_sure_local_model_is_enough_when_the_other_agrees(monkeypatch):
    triage, asked = make(
        monkeypatch, Engine(prediction({"a": 0.8, "b": 0.1, "c": 0.1}, 0.8)), Engine(prediction({"a": 0.5, "b": 0.3, "c": 0.2}, 0.5)),
    )
    answer, _ = run(triage)
    assert answer["resolved_by"] == "local" and answer["answer_confidence"] == 0.8 and asked == []


def test_local_models_that_disagree_ask_the_fallback_even_when_one_is_sure(monkeypatch):
    english = Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.9))
    typed = Engine(prediction({"a": 0.2, "b": 0.5, "c": 0.3}, 0.4))
    triage, asked = make(monkeypatch, english, typed, remote({"a": 0.3, "b": 0.4, "c": 0.3}, 0.5))

    answer, tokens = run(triage)

    # Confidences 0.9, 0.5, 0.4: the leader is 0.4 ahead of the next, so its answer stands as it is (phase 1).
    assert asked == [["a", "b", "c"]] and tokens == 25
    assert answer["choice"] == "a" and answer["answered_by"] == "laya-english" and answer["deferred_to"] == "laya-english"
    assert answer["probabilities"] == {"a": 0.9, "b": 0.05, "c": 0.05} and answer["resolved_by"] == "gap"
    assert steps(answer) == ["laya-english", "laya-typed", "jev", "gap"] and answer["rounds"][-1]["gap"] == 0.4
    assert cases.path_of(answer) == "deferred->laya-english"


def test_agreeing_but_unsure_local_models_still_ask_the_fallback_and_blend_all_three(monkeypatch):
    english = Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5))
    typed = Engine(prediction({"a": 0.4, "b": 0.3, "c": 0.3}, 0.6))
    triage, asked = make(monkeypatch, english, typed, remote({"a": 0.4, "b": 0.35, "c": 0.25}, 0.55))

    answer, _ = run(triage)

    assert asked == [["a", "b", "c"]]
    assert answer["answered_by"] == "laya-english+laya-typed+jev" and answer["resolved_by"] == "blend"
    assert answer["choice"] == "a" and answer["answer_confidence"] == 0.6 and answer["uncertain"] is True
    assert "disagreement" not in answer and steps(answer) == ["laya-english", "laya-typed", "jev", "average"]
    assert cases.path_of(answer) == "blend"


# --- phase 2: average, drop, ask again -------------------------------------------------------------

def disagreeing_first_round():
    english = {"a": 0.5, "b": 0.4, "c": 0.1}   # picks a at 0.5
    typed = {"a": 0.4, "b": 0.5, "c": 0.1}     # picks b at 0.45
    fallback = {"a": 0.45, "b": 0.5, "c": 0.05}  # picks b at 0.4
    return english, typed, fallback


def test_the_first_sure_voter_decides_the_narrowed_question(monkeypatch):
    e, t, j = disagreeing_first_round()
    english = Engine(prediction(e, 0.5), prediction({"a": 0.8, "b": 0.2}, 0.8))
    typed = Engine(prediction(t, 0.45))
    triage, asked = make(monkeypatch, english, typed, remote(j, 0.4))

    answer, _ = run(triage)

    assert english.calls == [["a", "b", "c"], ["a", "b"]] and typed.calls == [["a", "b", "c"]]  # typed was not asked again
    assert asked == [["a", "b", "c"]]  # nor was the fallback
    assert answer["choice"] == "a" and answer["answered_by"] == "laya-english" and answer["eliminated"] == ["c"]
    assert answer["probabilities"] == {"a": 0.8, "b": 0.2, "c": 0.0} and answer["uncertain"] is False
    assert steps(answer) == ["laya-english", "laya-typed", "jev", "average", "laya-english"]
    assert answer["rounds"][3] == {
        "step": "average", "probabilities": {"a": 0.45, "b": 0.4667, "c": 0.0833}, "eliminated": ["c"],
    }
    assert cases.path_of(answer) == "narrowed->laya-english"


def test_the_narrowed_question_goes_down_the_voters_until_one_is_sure(monkeypatch):
    e, t, j = disagreeing_first_round()
    english = Engine(prediction(e, 0.5), prediction({"a": 0.55, "b": 0.45}, 0.4))
    typed = Engine(prediction(t, 0.45), prediction({"a": 0.3, "b": 0.7}, 0.75))
    triage, asked = make(monkeypatch, english, typed, remote(j, 0.4))

    answer, _ = run(triage)

    assert answer["choice"] == "b" and answer["answered_by"] == "laya-typed" and answer["uncertain"] is False
    assert steps(answer)[-2:] == ["laya-english", "laya-typed"] and asked == [["a", "b", "c"]]


def test_three_unsure_voters_over_two_options_use_the_pair_rule_on_the_spread(monkeypatch):
    english = Engine(
        prediction({"a": 0.5, "b": 0.45, "c": 0.05}, 0.5), prediction({"a": 0.95, "b": 0.05}, 0.65),
    )
    typed = Engine(prediction({"a": 0.4, "b": 0.5, "c": 0.1}, 0.45), prediction({"a": 0.45, "b": 0.55}, 0.4))
    triage, asked = make(
        monkeypatch, english, typed, remote({"a": 0.45, "b": 0.5, "c": 0.05}, 0.4), remote({"a": 0.44, "b": 0.56}, 0.4),
    )

    answer, _ = run(triage)

    # Weighed by confidence: english 0.6175 / 0.0325, typed 0.18 / 0.22, jev 0.176 / 0.224. The spread per option
    # (largest minus smallest) is 0.4415 for a and 0.1915 for b; 0.1915 is under half of 0.4415, so a wins.
    assert asked == [["a", "b", "c"], ["a", "b"]]
    assert answer["resolved_by"] == "pair" and answer["choice"] == "a" and answer["uncertain"] is False
    assert answer["probabilities"] == {"a": 0.6975, "b": 0.3025, "c": 0.0} and answer["answer_confidence"] == 0.6975
    assert answer["eliminated"] == ["c"] and answer["also_check"] == ["b"]
    assert answer["disagreement"] == {"laya-english": "a", "laya-typed": "b", "jev": "b"}
    assert answer["answered_by"] == "laya-english+laya-typed+jev"
    assert steps(answer)[-4:] == ["laya-english x confidence", "laya-typed x confidence", "jev x confidence", "difference"]
    assert answer["rounds"][-1]["probabilities"] == {"a": 0.4415, "b": 0.1915}
    assert cases.path_of(answer) == "narrowed->pair"


def test_close_spreads_leave_both_options_open(monkeypatch):
    english = Engine(prediction({"a": 0.5, "b": 0.45, "c": 0.05}, 0.5), prediction({"a": 0.6, "b": 0.4}, 0.5))
    typed = Engine(prediction({"a": 0.4, "b": 0.5, "c": 0.1}, 0.45), prediction({"a": 0.3, "b": 0.7}, 0.5))
    triage, _ = make(monkeypatch, english, typed, remote({"a": 0.45, "b": 0.5, "c": 0.05}, 0.4), remote({"a": 0.2, "b": 0.8}, 0.5))

    answer, _ = run(triage)

    # Spreads: a 0.30 - 0.10 = 0.20 and b 0.40 - 0.20 = 0.20: nothing to choose between them.
    assert answer["uncertain"] is True and answer["candidates"] == ["a", "b"] and answer["resolved_by"] == "pair"
    assert "check both" in answer["note"]


# --- two options from the start, odd inputs ---------------------------------------------------------

def test_a_two_option_question_that_still_disagrees_goes_straight_to_the_pair_rule(monkeypatch):
    options = {"a": "A", "b": "B"}
    english = Engine(prediction({"a": 0.9, "b": 0.1}, 0.65))
    typed = Engine(prediction({"a": 0.45, "b": 0.55}, 0.4))
    triage, _ = make(monkeypatch, english, typed, remote({"a": 0.44, "b": 0.56}, 0.4))

    answer, _ = run(triage, request_json(options))

    # The same numbers as above with nothing to drop: a clear winner, and the other option to check.
    assert answer["resolved_by"] == "pair" and answer["choice"] == "a" and "eliminated" not in answer
    assert answer["also_check"] == ["b"] and cases.path_of(answer) == "pair"


def test_a_text_neither_laya_model_can_read_goes_to_the_fallback_alone(monkeypatch):
    unreadable = prediction({"a": 0.5, "b": 0.3, "c": 0.2}, 0.5)
    unreadable["usage"]["truncated"] = True
    triage, asked = make(monkeypatch, Engine(unreadable), Engine(unreadable), remote({"a": 0.9, "b": 0.05, "c": 0.05}, 0.9))

    answer, _ = run(triage)

    assert asked == [["a", "b", "c"]] and answer["answered_by"] == "jev" and answer["choice"] == "a"
    assert cases.path_of(answer) == "fallback"


def test_one_local_model_failing_leaves_the_other_and_the_fallback_to_vote(monkeypatch):
    english = Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5))
    triage, _ = make(monkeypatch, english, Engine(error=ValueError("boom")), remote({"a": 0.4, "b": 0.35, "c": 0.25}, 0.55))

    answer, _ = run(triage)

    assert answer["answered_by"] == "laya-english+jev" and answer["answer_confidence"] == 0.55


def test_with_the_fallback_off_only_the_two_local_models_vote(monkeypatch):
    english = Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5))
    typed = Engine(prediction({"a": 0.4, "b": 0.3, "c": 0.3}, 0.55))
    triage, asked = make(monkeypatch, english, typed, use_fallback=False)

    answer, _ = run(triage)

    assert asked == [] and answer["answered_by"] == "laya-english+laya-typed" and answer["uncertain"] is True
    assert answer["answer_confidence"] == 0.55


def test_a_lone_unsure_local_model_answers_as_it_is_with_no_fallback(monkeypatch):
    triage, _ = make(monkeypatch, Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5)), Engine(error=ValueError("x")), use_fallback=False)

    answer, _ = run(triage)

    assert answer["answered_by"] == "laya-english" and answer["uncertain"] is True and cases.path_of(answer) == "laya"


def test_score_and_noul_questions_take_the_first_sure_local_answer_else_the_fallbacks(monkeypatch):
    def noul(value, confidence):
        return {
            "answers": {"area": {"noul": value, "answer_confidence": confidence}},
            "usage": {"input_tokens": 7, "output_tokens": 0, "state_tokens": 1, "truncated": False},
        }

    class NoulEngine(Engine):
        def predict(self, state, questions, **kwargs):
            self.calls.append([])
            return copy.deepcopy(self.results.pop(0))

    raw = json.dumps({"text": "t", "questions": {"area": {"type": "noul", "instructions": "Is it?"}}})

    sure, asked = make(monkeypatch, NoulEngine(noul(0.9, 0.9)), NoulEngine(noul(0.8, 0.5)))
    answer, tokens = run(sure, raw)
    assert answer["noul"] == 0.9 and answer["answered_by"] == "laya-english" and asked == [] and tokens == 14

    unsure, asked = make(
        monkeypatch, NoulEngine(noul(0.6, 0.5)), NoulEngine(noul(0.7, 0.55)),
        {"type": "noul", "noul": 0.95, "answer_confidence": 0.95, "uncertain": False, "answered_by": "jev"},
    )
    answer, _ = run(unsure, raw)
    assert answer["noul"] == 0.95 and answer["answered_by"] == "jev" and len(asked) == 1


# --- wiring into the script ---------------------------------------------------------------------------

def test_the_three_way_flag_loads_both_checkpoints_and_uses_the_fallback_unless_baseline(monkeypatch, capsys):
    loaded = []

    class FakeThreeWay:
        def prepare(self):
            pass

        def answer(self, raw):
            answers = {"category": {"type": "choice", "choice": "unknown", "answer_confidence": 0.9, "uncertain": False}}
            return type("R", (), {"response": json.dumps({"answers": answers}), "input_tokens": 5})()

    monkeypatch.setattr(cases, "load_env", lambda: None)
    monkeypatch.setattr(decision, "settings", decision.settings)  # main() replaces it; this restores it afterwards
    monkeypatch.setattr(three.ThreeWayTriage, "load", classmethod(lambda cls, max_len, use_fallback=True: loaded.append((max_len, use_fallback)) or FakeThreeWay()))

    assert cases.main(["--case", "vague", "--three-way"]) == 0
    assert cases.main(["--case", "vague", "--three-way", "--max-len", "2048", "--baseline"]) == 0

    assert loaded == [(4096, True), (2048, False)]
    assert "vague" in capsys.readouterr().out


def test_the_step_names_of_the_three_voters_read_well_in_the_rounds_table():
    answer = {
        "type": "choice", "choice": "a", "probabilities": {"a": 0.8, "b": 0.2}, "answer_confidence": 0.8, "uncertain": False,
        "answered_by": "laya-english+laya-typed", "resolved_by": "local",
        "rounds": [
            {"step": "laya-english", "choice": "a", "probabilities": {"a": 0.9, "b": 0.1}, "confidence": 0.9},
            {"step": "laya-typed", "choice": "a", "probabilities": {"a": 0.7, "b": 0.3}, "confidence": 0.7},
        ],
    }
    row = cases.Row("x", "q", "", "a", None, "local", 2, 0.8, False, 10, 0.1, answer)

    text = cases.rounds_table(row)

    assert "Laya (English)" in text and "Laya (typed)" in text
