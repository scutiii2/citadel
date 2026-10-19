"""scripts/triage_three_way.py: Laya English first, Laya typed-decisions next, the fallback last, each against
its own confidence threshold."""

from __future__ import annotations

import copy
import json

import pytest

from scripts import check_triage_cases as cases
from scripts import triage_three_way as three
from src.llm import decision, laya_provider, triage_flow
from src.llm.laya_provider import LayaQuestions

OPTIONS = {"a": "A", "b": "B", "c": "C"}
TWO = {"a": "A", "b": "B"}


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


def make(monkeypatch, english, typed, *fallback, use_fallback=True, thresholds=None, **settings):
    """A ThreeWayTriage over scripted engines; `fallback` are Jev's answers in order. Returns it and the options
    Jev was asked about, one list per call."""
    config = decision.ClassifierSettings(triage_fallback=True, **settings)
    monkeypatch.setattr(decision, "settings", lambda: config)
    monkeypatch.setattr(decision, "available", lambda *a, **k: True)
    queue, asked = list(fallback), []

    def ask_fallback(request, qids):
        asked.append(list(request.questions[qids[0]].get("criteria", {})))
        outcome = queue.pop(0)
        return ({qids[0]: outcome} if outcome else {}), 5, []

    monkeypatch.setattr(laya_provider, "_ask_fallback", ask_fallback)
    triage = three.ThreeWayTriage(
        {three.ENGLISH: LayaQuestions(english), three.TYPED: LayaQuestions(typed)}, use_fallback, thresholds,
    )
    return triage, asked


def run(triage, raw=None):
    result = triage.answer(raw or request_json())
    return json.loads(result.response)["answers"]["area"], result.input_tokens


def steps(answer):
    return [r["step"] for r in answer["rounds"]]


# --- 1 and 2: the two local models ------------------------------------------------------------------

def test_a_sure_english_answer_is_taken_and_nothing_else_is_asked(monkeypatch):
    english = Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.8))
    typed = Engine()
    triage, asked = make(monkeypatch, english, typed)

    answer, tokens = run(triage)

    assert answer["choice"] == "a" and answer["answered_by"] == "laya-english" and answer["resolved_by"] == "local"
    assert answer["uncertain"] is False and typed.calls == [] and asked == [] and tokens == 10
    assert "rounds" not in answer  # one model answered: no trace to read
    assert cases.path_of(answer) == "local"


def test_typed_is_asked_only_when_english_is_not_sure_and_a_matching_sure_typed_answer_wins(monkeypatch):
    english = Engine(prediction({"a": 0.5, "b": 0.3, "c": 0.2}, 0.5))
    typed = Engine(prediction({"a": 0.6, "b": 0.25, "c": 0.15}, 0.6))
    triage, asked = make(monkeypatch, english, typed)

    answer, tokens = run(triage)

    assert answer["choice"] == "a" and answer["answered_by"] == "laya-english+laya-typed" and answer["answer_confidence"] == 0.6
    assert answer["probabilities"] == {"a": 0.6, "b": 0.25, "c": 0.15}  # typed's own answer
    assert steps(answer) == ["laya-english", "laya-typed"] and [r["threshold"] for r in answer["rounds"]] == [0.75, 0.55]
    assert asked == [] and tokens == 20


def test_a_typed_answer_that_disagrees_with_english_is_not_taken_even_when_sure(monkeypatch):
    english = Engine(prediction({"a": 0.5, "b": 0.3, "c": 0.2}, 0.5))
    typed = Engine(prediction({"a": 0.1, "b": 0.7, "c": 0.2}, 0.7))
    triage, asked = make(monkeypatch, english, typed, remote({"a": 0.9, "b": 0.05, "c": 0.05}, 0.95))

    answer, _ = run(triage)

    assert answer["choice"] == "a" and answer["answered_by"] == "jev"  # it went on to Jev, which was sure
    assert asked == [["a", "b", "c"]]


def test_typed_alone_is_taken_when_english_could_not_answer(monkeypatch):
    triage, _ = make(monkeypatch, Engine(error=ValueError("too long")), Engine(prediction({"a": 0.7, "b": 0.2, "c": 0.1}, 0.6)))

    answer, _ = run(triage)

    assert answer["answered_by"] == "laya-typed" and answer["choice"] == "a"


def test_the_thresholds_depend_on_the_number_of_options(monkeypatch):
    # English at 0.85 is sure with three options (needs 0.75) but not with two (needs 0.90).
    three_options, _ = make(monkeypatch, Engine(prediction({"a": 0.85, "b": 0.1, "c": 0.05}, 0.85)), Engine())
    assert run(three_options)[0]["resolved_by"] == "local"

    typed = Engine(prediction({"a": 0.9, "b": 0.1}, 0.85))
    two_options, asked = make(monkeypatch, Engine(prediction({"a": 0.85, "b": 0.15}, 0.85)), typed)
    answer, _ = run(two_options, request_json(TWO))
    # typed (needs 0.80 with two options) is asked and agrees at 0.85
    assert typed.calls == [["a", "b"]] and answer["answered_by"] == "laya-english+laya-typed" and asked == []


def test_a_threshold_can_be_changed_and_a_request_can_replace_all_of_them(monkeypatch):
    unsure = [prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.8), prediction({"a": 0.95, "b": 0.05}, 0.8)]
    triage, _ = make(monkeypatch, Engine(*unsure), Engine(*unsure),
                     use_fallback=False, thresholds={"3+": {three.ENGLISH: 0.95, three.TYPED: 0.95}})
    answer, _ = run(triage)
    assert answer["resolved_by"] != "local"  # 0.8 no longer meets 0.95 for either model

    lenient, _ = make(monkeypatch, Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.6)), Engine())
    answer, _ = run(lenient, request_json(min_confidence=0.5))
    assert answer["answered_by"] == "laya-english" and answer["resolved_by"] == "local"  # 0.6 meets the request's 0.5


# --- 3: drop the clearly worse options and ask the local models again ------------------------------------

def test_options_far_below_the_best_are_dropped_and_english_decides_the_narrowed_question(monkeypatch):
    english = Engine(prediction({"a": 0.5, "b": 0.4, "c": 0.1}, 0.5), prediction({"a": 0.95, "b": 0.05}, 0.92))
    typed = Engine(prediction({"a": 0.4, "b": 0.5, "c": 0.1}, 0.45))
    triage, asked = make(monkeypatch, english, typed)

    answer, tokens = run(triage)

    assert english.calls == [["a", "b", "c"], ["a", "b"]] and typed.calls == [["a", "b", "c"]]
    assert asked == [] and tokens == 30
    assert answer["choice"] == "a" and answer["answered_by"] == "laya-english" and answer["resolved_by"] == "narrowed"
    assert answer["eliminated"] == ["c"] and answer["probabilities"] == {"a": 0.95, "b": 0.05, "c": 0.0}
    assert steps(answer) == ["laya-english", "laya-typed", "average", "laya-english"]
    assert answer["rounds"][2] == {"step": "average", "probabilities": {"a": 0.45, "b": 0.45, "c": 0.1}, "eliminated": ["c"]}
    assert answer["rounds"][3]["options"] == ["a", "b"] and answer["rounds"][3]["threshold"] == 0.9  # two options now
    assert cases.path_of(answer) == "narrowed->laya-english"


def test_typed_decides_the_narrowed_question_when_english_is_still_not_sure(monkeypatch):
    english = Engine(prediction({"a": 0.5, "b": 0.4, "c": 0.1}, 0.5), prediction({"a": 0.6, "b": 0.4}, 0.5))
    typed = Engine(prediction({"a": 0.4, "b": 0.5, "c": 0.1}, 0.45), prediction({"a": 0.1, "b": 0.9}, 0.85))
    triage, asked = make(monkeypatch, english, typed)

    answer, _ = run(triage)

    assert answer["choice"] == "b" and answer["answered_by"] == "laya-typed" and answer["eliminated"] == ["c"] and asked == []


def test_narrowing_repeats_while_options_can_still_be_dropped(monkeypatch):
    four = {"a": "A", "b": "B", "c": "C", "d": "D"}
    english = Engine(
        prediction({"a": 0.4, "b": 0.35, "c": 0.17, "d": 0.08}, 0.5),  # the average drops d (0.08 < a quarter of 0.4), then ...
        prediction({"a": 0.55, "b": 0.4, "c": 0.05}, 0.5),             # ... c (the new average is 0.05 against 0.525)
        prediction({"a": 0.95, "b": 0.05}, 0.95),
    )
    typed = Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.17, "d": 0.08}, 0.4), prediction({"a": 0.5, "b": 0.45, "c": 0.05}, 0.4))
    triage, _ = make(monkeypatch, english, typed)

    answer, _ = run(triage, request_json(four))

    assert english.calls == [["a", "b", "c", "d"], ["a", "b", "c"], ["a", "b"]]
    assert typed.calls == [["a", "b", "c", "d"], ["a", "b", "c"]]
    assert answer["eliminated"] == ["d", "c"] and answer["answered_by"] == "laya-english" and answer["choice"] == "a"


# --- 4: Jev, then Jev again over a narrower set --------------------------------------------------------

def test_jev_is_asked_on_all_options_when_none_can_be_dropped_and_a_sure_jev_decides(monkeypatch):
    english = Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5))
    typed = Engine(prediction({"a": 0.3, "b": 0.4, "c": 0.3}, 0.5))
    triage, asked = make(monkeypatch, english, typed, remote({"a": 0.95, "b": 0.03, "c": 0.02}, 0.93))

    answer, tokens = run(triage)

    assert asked == [["a", "b", "c"]] and tokens == 25
    assert answer["choice"] == "a" and answer["answered_by"] == "jev" and answer["resolved_by"] == "jev"
    assert steps(answer) == ["laya-english", "laya-typed", "jev"] and answer["rounds"][-1]["threshold"] == 0.9
    assert cases.path_of(answer) == "fallback"


def test_an_unsure_jev_is_asked_again_over_options_narrowed_by_all_the_models(monkeypatch):
    english = Engine(prediction({"a": 0.42, "b": 0.43, "c": 0.15}, 0.5))
    typed = Engine(prediction({"a": 0.32, "b": 0.53, "c": 0.15}, 0.5))
    triage, asked = make(
        monkeypatch, english, typed, remote({"a": 0.5, "b": 0.48, "c": 0.02}, 0.6), remote({"a": 0.05, "b": 0.95}, 0.93),
    )

    answer, _ = run(triage)

    # Locally c is not far enough below (0.15 against a leader of 0.48); with Jev's 0.02 the three-way average is.
    assert asked == [["a", "b", "c"], ["a", "b"]]
    assert answer["choice"] == "b" and answer["answered_by"] == "jev" and answer["eliminated"] == ["c"]
    assert answer["probabilities"] == {"a": 0.05, "b": 0.95, "c": 0.0}
    assert steps(answer) == ["laya-english", "laya-typed", "jev", "average", "jev"]
    assert cases.path_of(answer) == "narrowed->jev"


def test_a_text_neither_laya_model_can_read_goes_to_jev_alone(monkeypatch):
    unreadable = prediction({"a": 0.5, "b": 0.3, "c": 0.2}, 0.5)
    unreadable["usage"]["truncated"] = True
    triage, asked = make(monkeypatch, Engine(unreadable), Engine(unreadable), remote({"a": 0.95, "b": 0.03, "c": 0.02}, 0.93))

    answer, _ = run(triage)

    assert asked == [["a", "b", "c"]] and answer["answered_by"] == "jev" and answer["uncertain"] is False
    assert any("failed" in r for r in answer["rounds"])


# --- 5: nobody is sure: compare what they said -------------------------------------------------------------

def test_the_pairwise_comparison_decides_when_one_option_clearly_stands_out(monkeypatch):
    english = Engine(prediction({"a": 0.5, "b": 0.4, "c": 0.1}, 0.5), prediction({"a": 0.6, "b": 0.4}, 0.5))
    typed = Engine(prediction({"a": 0.3, "b": 0.6, "c": 0.1}, 0.6), prediction({"a": 0.45, "b": 0.55}, 0.6))
    triage, asked = make(monkeypatch, english, typed, remote({"a": 0.49, "b": 0.51}, 0.6))

    answer, _ = run(triage)

    # Weighted by confidence: English 0.30 / 0.20, typed 0.27 / 0.33, Jev 0.294 / 0.306. Mean of the three pairwise
    # differences: a 0.02, b 0.0867. 0.02 is under half of 0.0867, so b is the answer and a is the one to check.
    assert asked == [["a", "b"]]
    assert answer["resolved_by"] == "final" and answer["choice"] == "b" and answer["uncertain"] is True
    assert answer["eliminated"] == ["c"] and answer["also_check"] == ["a"] and "unknown" not in answer
    assert answer["probabilities"] == {"a": 0.1875, "b": 0.8125, "c": 0.0} and answer["answer_confidence"] == 0.8125
    assert steps(answer) == [
        "laya-english", "laya-typed", "average", "laya-english", "laya-typed", "jev",
        "laya-english x confidence", "laya-typed x confidence", "jev x confidence", "difference",
    ]
    assert answer["rounds"][-1]["probabilities"] == {"a": 0.02, "b": 0.0867}
    assert answer["disagreement"] == {"laya-english": "a", "laya-typed": "b", "jev": "b"}
    assert cases.path_of(answer) == "narrowed->final"


def test_close_values_make_the_answer_unknown_between_the_two_options(monkeypatch):
    triage, _ = make(
        monkeypatch, Engine(prediction({"a": 0.7, "b": 0.3}, 0.6)), Engine(prediction({"a": 0.4, "b": 0.6}, 0.5)), use_fallback=False,
    )

    answer, _ = run(triage, request_json(TWO))

    # English 0.42 / 0.18, typed 0.20 / 0.30: differences 0.22 and 0.12, and 0.12 is not under half of 0.22.
    assert answer["unknown"] is True and answer["uncertain"] is True and answer["candidates"] == ["a", "b"]
    assert answer["note"] == "The answer is unknown: it could be a or b; check both." and answer["choice"] == "a"
    assert answer["rounds"][-1]["choice"] == "unknown: a or b" and cases.path_of(answer) == "final"


def test_without_jev_the_two_local_models_are_compared_alone(monkeypatch):
    triage, asked = make(
        monkeypatch, Engine(prediction({"a": 0.7, "b": 0.3}, 0.6)), Engine(prediction({"a": 0.45, "b": 0.55}, 0.3)), use_fallback=False,
    )

    answer, _ = run(triage, request_json(TWO))

    # English 0.42 / 0.18, typed 0.135 / 0.165: differences 0.285 and 0.015.
    assert asked == [] and answer["choice"] == "a" and answer["uncertain"] is True and answer["also_check"] == ["b"]
    assert answer["answered_by"] == "laya-english+laya-typed" and answer["probabilities"] == {"a": 0.95, "b": 0.05}


def test_a_lone_unsure_voter_answers_as_it_is(monkeypatch):
    triage, _ = make(monkeypatch, Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5)), Engine(error=ValueError("x")), use_fallback=False)

    answer, _ = run(triage)

    assert answer["answered_by"] == "laya-english" and answer["uncertain"] is True


def test_a_decided_final_answer_is_still_uncertain_and_keeps_also_check(monkeypatch):
    triage, _ = make(
        monkeypatch, Engine(prediction({"a": 0.7, "b": 0.3}, 0.6)), Engine(prediction({"a": 0.45, "b": 0.55}, 0.3)), use_fallback=False,
    )

    result = json.loads(triage.answer(request_json(TWO)).response)

    assert result["uncertain"] is True and result["answers"]["area"]["uncertain"] is True
    assert result["answers"]["area"]["also_check"] == ["b"] and "unknown" not in result["answers"]["area"]


def test_a_failed_model_s_reason_reaches_the_error_when_nobody_answers(monkeypatch):
    triage, _ = make(
        monkeypatch, Engine(error=RuntimeError("Laya is not installed")), Engine(error=ValueError("bad window")), use_fallback=False,
    )

    with pytest.raises(ValueError, match=r"no model could answer 'area' \(laya-english: Laya is not installed; laya-typed: bad window\)"):
        run(triage)


def test_step_5_choice_is_never_an_eliminated_option():
    voter = {"type": "choice", "choice": "c", "probabilities": {"a": 0.3, "b": 0.2, "c": 0.5}, "answer_confidence": 0.5}

    restricted = triage_flow._restrict(voter, ["a", "b"])

    assert restricted["choice"] == "a" and restricted["probabilities"] == {"a": 0.6, "b": 0.4}
    assert triage_flow._restrict(voter, ["b", "c"])["choice"] == "c"


def test_a_local_only_request_never_reaches_jev_even_when_the_flow_allows_it(monkeypatch):
    english = Engine(prediction({"a": 0.5, "b": 0.3, "c": 0.2}, 0.5), prediction({"a": 0.6, "b": 0.4}, 0.5))
    typed = Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5), prediction({"a": 0.55, "b": 0.45}, 0.5))
    triage, asked = make(monkeypatch, english, typed, use_fallback=True)

    answer, _ = run(triage, request_json(local_only=True))

    assert asked == [] and "jev" not in answer["answered_by"] and answer["uncertain"] is True


# --- score and noul questions, odd inputs --------------------------------------------------------------------

def noul(value, confidence):
    return {
        "answers": {"area": {"noul": value, "answer_confidence": confidence}},
        "usage": {"input_tokens": 7, "output_tokens": 0, "state_tokens": 1, "truncated": False},
    }


def score(value, confidence):
    return {
        "answers": {"area": {"score": value, "answer_confidence": confidence}},
        "usage": {"input_tokens": 7, "output_tokens": 0, "state_tokens": 1, "truncated": False},
    }


class NoulEngine(Engine):
    def predict(self, state, questions, **kwargs):
        self.calls.append([])
        return copy.deepcopy(self.results.pop(0))


NOUL_REQUEST = json.dumps({"text": "t", "questions": {"area": {"type": "noul", "instructions": "Is it?"}}})


def test_a_score_question_takes_the_first_model_that_meets_its_threshold(monkeypatch):
    request = json.dumps({"text": "t", "questions": {"area": {"type": "score", "instructions": "How much?", "criteria": ["a", "b", "c"]}}})
    english, typed = NoulEngine(score(1.0, 0.9)), NoulEngine()
    triage, _ = make(monkeypatch, english, typed)
    answer, _ = run(triage, request)
    assert answer["answered_by"] == "laya-english" and typed.calls == []


def test_a_noul_question_never_asks_english(monkeypatch):
    english, typed = NoulEngine(), NoulEngine(noul(0.9, 0.9))
    triage, asked = make(monkeypatch, english, typed)

    answer, tokens = run(triage, NOUL_REQUEST)

    assert answer["noul"] == 0.9 and answer["answered_by"] == "laya-typed" and english.calls == [] and asked == [] and tokens == 7


def test_a_noul_question_needs_typeds_two_option_threshold(monkeypatch):
    triage, _ = make(monkeypatch, NoulEngine(), NoulEngine(noul(0.9, 0.7)), use_fallback=False)  # 0.7 passes 0.55, not 0.80

    answer, _ = run(triage, NOUL_REQUEST)

    assert answer["uncertain"] is True


def test_an_unsure_noul_question_without_the_fallback_is_typeds_answer_flagged_uncertain(monkeypatch):
    english, typed = NoulEngine(), NoulEngine(noul(0.7, 0.4))
    triage, asked = make(monkeypatch, english, typed, use_fallback=False)

    answer, _ = run(triage, NOUL_REQUEST)

    assert answer["noul"] == 0.7 and answer["answered_by"] == "laya-typed" and answer["uncertain"] is True
    assert english.calls == [] and asked == []


def test_an_unsure_noul_question_goes_to_jev_and_is_flagged_by_its_threshold(monkeypatch):
    jev = {"type": "noul", "noul": 0.95, "answer_confidence": 0.8, "uncertain": False, "answered_by": "jev"}
    triage, asked = make(monkeypatch, NoulEngine(), NoulEngine(noul(0.7, 0.4)), jev)

    answer, _ = run(triage, NOUL_REQUEST)

    assert answer["answered_by"] == "jev" and answer["uncertain"] is True and len(asked) == 1  # 0.8 is under Jev's 0.9


# --- which models answer which question type, and in what order (classifier.triage_enabled / triage_order) ---------

def only(voter_kinds):
    """A triage_enabled setting with everything on except the listed `voter: [types]` pairs."""
    enabled = {v: dict(t) for v, t in decision.DEFAULT_TRIAGE_ENABLED.items()}
    for voter, kinds in voter_kinds.items():
        for kind in kinds:
            enabled[voter][kind] = False
    return enabled


def test_a_choice_question_skips_a_model_switched_off_for_choice(monkeypatch):
    english, typed = Engine(), Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.8))
    triage, _ = make(monkeypatch, english, typed, triage_enabled=only({"laya-english": ["choice"]}))

    answer, _ = run(triage)

    assert answer["answered_by"] == "laya-typed" and english.calls == []


def test_a_choice_question_asks_the_local_models_in_the_configured_order(monkeypatch):
    english = Engine()
    typed = Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.8))
    order = {"choice": ("laya-typed", "laya-english", "jev")}
    triage, _ = make(monkeypatch, english, typed, triage_order={**decision.DEFAULT_TRIAGE_ORDER, **order})

    answer, _ = run(triage)

    assert answer["answered_by"] == "laya-typed" and english.calls == []


def test_a_choice_question_never_asks_jev_when_jev_is_switched_off_for_choice(monkeypatch):
    english = Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.4))
    typed = Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.4))
    triage, asked = make(monkeypatch, english, typed, triage_enabled=only({"jev": ["choice"]}))

    answer, _ = run(triage, request_json(OPTIONS))

    assert asked == [] and answer["uncertain"] is True


def test_a_noul_question_follows_the_configured_order(monkeypatch):
    typed = Engine()
    jev = {"type": "noul", "noul": 0.95, "answer_confidence": 0.95, "uncertain": False, "answered_by": "jev"}
    triage, asked = make(monkeypatch, Engine(), typed, jev, triage_order={**decision.DEFAULT_TRIAGE_ORDER, "noul": ("jev", "laya-typed")})

    answer, _ = run(triage, NOUL_REQUEST)

    assert answer["answered_by"] == "jev" and answer["uncertain"] is False and typed.calls == []


def test_english_can_be_switched_on_for_noul(monkeypatch):
    english = NoulEngine(noul(0.9, 0.95))
    order = {**decision.DEFAULT_TRIAGE_ORDER, "noul": ("laya-english", "laya-typed")}
    triage, _ = make(monkeypatch, english, NoulEngine(), triage_order=order)

    answer, _ = run(triage, NOUL_REQUEST)

    assert answer["answered_by"] == "laya-english"


def test_a_noul_question_with_jev_switched_off_never_asks_jev(monkeypatch):
    triage, asked = make(monkeypatch, Engine(), NoulEngine(noul(0.7, 0.4)), triage_enabled=only({"jev": ["noul"]}))

    answer, _ = run(triage, NOUL_REQUEST)

    assert asked == [] and answer["answered_by"] == "laya-typed" and answer["uncertain"] is True


def test_a_score_question_skips_a_model_switched_off_for_score(monkeypatch):
    request = json.dumps({"text": "t", "questions": {"area": {"type": "score", "instructions": "How much?", "criteria": ["a", "b", "c"]}}})
    english, typed = NoulEngine(), NoulEngine(score(1.0, 0.9))
    triage, _ = make(monkeypatch, english, typed, triage_enabled=only({"laya-english": ["score"]}))

    answer, _ = run(triage, request)

    assert answer["answered_by"] == "laya-typed" and english.calls == []


# --- the script's wiring ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, parsed", [
    ("laya-typed:3+=0.6", ("laya-typed", "3+", 0.6)), ("jev:2=0.95", ("jev", "2", 0.95)), ("laya-english:2=1", ("laya-english", "2", 1.0)),
])
def test_threshold_flags_are_parsed(text, parsed):
    assert three.parse_threshold(text) == parsed


@pytest.mark.parametrize("text", ["laya-typed=0.6", "laya-typed:3+", "gpt:2=0.5", "jev:4=0.5", "jev:2=0", "jev:2=1.5", "jev:2=x"])
def test_bad_threshold_flags_are_refused(text):
    with pytest.raises(SystemExit, match="threshold"):
        three.parse_threshold(text)


def test_the_three_way_flags_reach_the_loader(monkeypatch, capsys):
    loaded = []

    class FakeThreeWay:
        def prepare(self):
            pass

        def answer(self, raw):
            answers = {"category": {"type": "choice", "choice": "unknown", "answer_confidence": 0.9, "uncertain": False}}
            return type("R", (), {"response": json.dumps({"answers": answers}), "input_tokens": 5})()

    def load(cls, max_len, use_fallback=True, thresholds=None):
        loaded.append((max_len, use_fallback, thresholds))
        return FakeThreeWay()

    monkeypatch.setattr(cases, "load_env", lambda: None)
    monkeypatch.setattr(decision, "settings", decision.settings)  # main() replaces it; this restores it afterwards
    monkeypatch.setattr(three.ThreeWayTriage, "load", classmethod(load))

    assert cases.main(["--case", "vague", "--three-way"]) == 0
    assert cases.main(["--case", "vague", "--three-way", "--max-len", "2048", "--baseline",
                       "--threshold", "laya-typed:3+=0.6", "--threshold", "jev:2=0.95"]) == 0

    assert loaded == [(4096, True, {}), (2048, False, {"3+": {"laya-typed": 0.6}, "2": {"jev": 0.95}})]
    assert "vague" in capsys.readouterr().out


def test_the_rounds_table_shows_what_each_model_needed_and_the_unknown_answer():
    answer = {
        "type": "choice", "choice": "a", "probabilities": {"a": 0.6, "b": 0.4}, "answer_confidence": 0.6, "uncertain": True,
        "unknown": True, "candidates": ["a", "b"], "answered_by": "laya-english+laya-typed", "resolved_by": "final",
        "rounds": [
            {"step": "laya-english", "choice": "a", "probabilities": {"a": 0.7, "b": 0.3}, "confidence": 0.6, "threshold": 0.9},
            {"step": "laya-typed", "choice": "b", "probabilities": {"a": 0.4, "b": 0.6}, "confidence": 0.5, "threshold": 0.8},
        ],
    }
    row = cases.Row("x", "q", "", "a", None, "final", 2, 0.6, True, 10, 0.1, answer)

    text = cases.rounds_table(row)

    assert "Laya (English)" in text and "Laya (typed)" in text and "| Needs |" in text
    assert text.splitlines()[-1] == "answer: unknown (could be a or b)"
