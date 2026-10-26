"""The Triage Assistant's flow (llm/triage_flow.py): what Garrison asks the Laya service, and how it adds the
fallback classifier (Jev) to the answers the service could not settle. The local rules are the service's."""

from __future__ import annotations

import json

import pytest

from src.llm import decision, laya_model, laya_provider, triage_flow
from src.llm.laya_model import LayaServiceError
from src.llm.triage_flow import TriageFlow
from tests.fake_laya import FakeService, choice, result, unsure

OPTIONS = {"a": "A", "b": "B", "c": "C"}
VOTERS_ABC = {"laya-english": choice("a", 0.5), "laya-typed": choice("b", 0.5)}


def request_json(options=OPTIONS, **extra):
    return json.dumps({"text": "some text", "questions": {"area": {"type": "choice", "instructions": "Which?", "criteria": options}}, **extra})


def configure(monkeypatch, fallback=True, **changes):
    config = decision.ClassifierSettings(triage_fallback=fallback, **changes)
    monkeypatch.setattr(decision, "settings", lambda: config)
    monkeypatch.setattr(decision, "available", lambda *a, **k: fallback)
    return config


def jev(monkeypatch, *answers):
    """Script Jev's answers in order (None: it could not answer); returns the option lists Jev was asked about."""
    queue, asked = list(answers), []

    def ask_fallback(request, qids):
        asked.append(list(request.questions[qids[0]].get("criteria", {})))
        outcome = queue.pop(0)
        return ({qids[0]: outcome} if outcome else {}), 5, []

    monkeypatch.setattr(laya_provider, "_ask_fallback", ask_fallback)
    return asked


def jev_answer(pick, confidence, options=("a", "b", "c")):
    return {**choice(pick, confidence, options, by="jev"), "uncertain": confidence < 0.7}


def run(service, raw=None, question="area", **flow):
    result_ = TriageFlow(service=service, **flow).answer(raw or request_json())
    return json.loads(result_.response)["answers"][question], result_


# --- the settings ------------------------------------------------------------------------------------------

def use_section(monkeypatch, section):
    decision.reset_cache()
    monkeypatch.setattr(decision, "read_section", lambda path, name, default=None: section)


def test_the_flow_defaults(monkeypatch):
    use_section(monkeypatch, {})
    config = decision.settings()
    assert (config.triage_window, config.triage_thresholds) == (4096, {})
    assert config.triage_trace is False


def test_the_flow_window_and_thresholds_are_read(monkeypatch):
    use_section(monkeypatch, {
        "triage_window": 2048, "triage_trace": True,
        "triage_thresholds": {"2": {"laya-typed": 0.85}, "3+": {"jev": 0.8, "laya-english": 0.7}},
    })
    config = decision.settings()
    assert config.triage_window == 2048 and config.triage_trace is True
    assert config.triage_thresholds == {"2": {"laya-typed": 0.85}, "3+": {"jev": 0.8, "laya-english": 0.7}}


@pytest.mark.parametrize("section", [
    {"triage_window": 100}, {"triage_window": 99999}, {"triage_window": True},
    {"triage_window": "big"}, {"triage_thresholds": []}, {"triage_thresholds": {"4": {"jev": 0.9}}},
    {"triage_thresholds": {"2": []}}, {"triage_thresholds": {"2": {"gpt": 0.9}}}, {"triage_thresholds": {"2": {"jev": 0}}},
    {"triage_thresholds": {"2": {"jev": 1.5}}}, {"triage_thresholds": {"2": {"jev": True}}},
])
def test_a_bad_flow_setting_is_refused(monkeypatch, section):
    use_section(monkeypatch, section)
    with pytest.raises(ValueError, match="classifier"):
        decision.settings()
    decision.reset_cache()


# --- what the service is asked -------------------------------------------------------------------------------

def test_each_question_type_is_sent_with_the_strategy_its_local_voters_make(monkeypatch):
    configure(monkeypatch, fallback=False)
    service = FakeService(result(("area", choice("a", 0.9, uncertain=False)), ("problem", noul_answer(0.9, 0.9, False))))
    raw = json.dumps({"text": "t", "questions": {
        "area": {"type": "choice", "instructions": "Which?", "criteria": OPTIONS},
        "problem": {"type": "noul", "instructions": "Is it?"},
    }})
    TriageFlow(service=service).answer(raw)
    # noul skips English by default (its yes/no label bug), so typed alone answers it.
    assert [(c["strategy"], list(c["questions"])) for c in service.asked] == [
        ("english-then-typed", ["area"]), ("typed-only", ["problem"])]


@pytest.mark.parametrize("order, enabled, strategy", [
    (("laya-typed", "laya-english", "jev"), {}, "typed-then-english"),
    (("laya-english", "laya-typed", "jev"), {"laya-english": False}, "typed-only"),
    (("laya-english", "laya-typed", "jev"), {"laya-typed": False}, "english-only"),
])
def test_the_configured_order_and_switches_choose_the_strategy(monkeypatch, order, enabled, strategy):
    flags = {v: {k: enabled.get(v, True) for k in decision.TRIAGE_TYPES} for v in decision.TRIAGE_VOTERS}
    configure(monkeypatch, fallback=False, triage_order={**decision.DEFAULT_TRIAGE_ORDER, "choice": order}, triage_enabled=flags)
    service = FakeService(result(("area", choice("a", 0.9, uncertain=False))))
    run(service)
    assert service.asked[0]["strategy"] == strategy


def test_the_window_thresholds_and_ratios_reach_the_service_without_jevs_threshold(monkeypatch):
    configure(monkeypatch, fallback=False, triage_window=2048, triage_prune_ratio=0.3, triage_pair_ratio=0.6,
              triage_thresholds={"3+": {"laya-typed": 0.6, "jev": 0.8}})
    service = FakeService(result(("area", choice("a", 0.9, uncertain=False))))
    run(service, request_json(min_confidence=0.5))
    sent = service.asked[0]
    assert sent["max_len"] == 2048 and sent["prune_ratio"] == 0.3 and sent["pair_ratio"] == 0.6
    assert sent["min_confidence"] == 0.5
    assert sent["thresholds"]["3+"] == {"laya-english": 0.75, "laya-typed": 0.6}
    assert sent["thresholds"]["2"] == {"laya-english": 0.9, "laya-typed": 0.8}


def test_a_settled_answer_never_asks_jev_and_every_model_call_is_logged(monkeypatch):
    configure(monkeypatch)
    jev(monkeypatch)  # an empty queue: asking Jev would fail
    service = FakeService(result(("area", choice("a", 0.9, uncertain=False, resolved_by="local")), tokens=42))
    usage = []
    answer, chat = run(service, on_usage=usage.append)
    assert answer["choice"] == "a" and chat.input_tokens == 42
    assert [(u["provider_id"], u["model"], u["input_tokens"], u["ok"]) for u in usage] == [("laya", "convaiinnovations/laya", 42, True)]


def test_the_services_hand_over_fields_are_not_part_of_the_answer(monkeypatch):
    configure(monkeypatch, fallback=False, triage_trace=True)
    service = FakeService(result(("area", unsure("a", 0.5, voters=VOTERS_ABC))))
    answer, _ = run(service)
    assert "voters" not in answer and "options" not in answer and answer["uncertain"] is True


# --- when the service cannot settle it -----------------------------------------------------------------------

def test_without_the_fallback_an_unsure_service_answer_is_returned_as_it_is(monkeypatch):
    configure(monkeypatch, fallback=False)
    answer, _ = run(FakeService(result(("area", unsure("a", 0.5, voters=VOTERS_ABC, also_check=["b"])))))
    assert answer["choice"] == "a" and answer["uncertain"] is True and answer["also_check"] == ["b"]


def test_a_sure_jev_decides_over_the_options_the_service_left(monkeypatch):
    configure(monkeypatch)
    asked = jev(monkeypatch, jev_answer("a", 0.95))
    service = FakeService(result(("area", unsure("a", 0.5, ("a", "b"), voters=VOTERS_ABC, eliminated=["c"],
                                                  rounds=[{"step": "laya-english"}])), tokens=10))
    answer, chat = run(service, request_json(), trace=True)
    assert asked == [["a", "b"]] and chat.input_tokens == 15
    assert answer["answered_by"] == "jev" and answer["resolved_by"] == "narrowed" and answer["uncertain"] is False
    assert answer["eliminated"] == ["c"] and answer["rounds"][0] == {"step": "laya-english"}
    assert answer["rounds"][-1]["threshold"] == 0.9


def test_an_unsure_jev_is_asked_again_over_the_options_all_the_models_narrow_to(monkeypatch):
    configure(monkeypatch)
    asked = jev(monkeypatch, jev_answer("a", 0.6), jev_answer("b", 0.95, ("a", "b")))
    mixed = {"voters": {**VOTERS_ABC, "jev": jev_answer("a", 0.6)}, "average": {"a": 0.5, "b": 0.45, "c": 0.05},
             "kept": ["a", "b"]}
    service = FakeService(result(("area", unsure("a", 0.5, voters=VOTERS_ABC))), mixed=mixed)
    answer, _ = run(service, trace=True)
    assert asked == [["a", "b", "c"], ["a", "b"]]
    assert service.combined[0]["options"] == ["a", "b", "c"] and set(service.combined[0]["voters"]) == {"laya-english", "laya-typed", "jev"}
    assert answer["choice"] == "b" and answer["answered_by"] == "jev" and answer["eliminated"] == ["c"]
    assert answer["probabilities"]["c"] == 0.0


def test_when_nothing_can_be_dropped_the_services_comparison_decides(monkeypatch):
    configure(monkeypatch)
    asked = jev(monkeypatch, jev_answer("c", 0.6))
    final = {"type": "choice", "choice": "c", "probabilities": {"a": 0.2, "b": 0.2, "c": 0.6}, "answer_confidence": 0.6,
             "uncertain": True, "answered_by": "laya-english+laya-typed+jev", "resolved_by": "final", "also_check": ["a", "b"]}
    mixed = {"voters": {**VOTERS_ABC, "jev": jev_answer("c", 0.6)}, "average": {}, "kept": ["a", "b", "c"], "final": final}
    answer, _ = run(FakeService(result(("area", unsure("a", 0.5, voters=VOTERS_ABC))), mixed=mixed), trace=True)
    assert asked == [["a", "b", "c"]] and answer["resolved_by"] == "final" and answer["uncertain"] is True
    assert answer["also_check"] == ["a", "b"]


def test_a_jev_that_cannot_answer_leaves_the_services_answer(monkeypatch):
    configure(monkeypatch)
    jev(monkeypatch, None)
    service = FakeService(result(("area", unsure("a", 0.5, voters=VOTERS_ABC, unknown=True, candidates=["a", "b"]))))
    answer, _ = run(service)
    assert answer["unknown"] is True and not service.combined


def test_when_the_service_cannot_compare_jev_alone_answers_uncertain(monkeypatch):
    configure(monkeypatch)
    jev(monkeypatch, jev_answer("b", 0.6, ("a", "b")))
    service = FakeService(result(("area", unsure("a", 0.5, ("a", "b"), voters=VOTERS_ABC))),
                          mixed=LayaServiceError("down"))
    answer, _ = run(service, request_json({"a": "A", "b": "B"}))
    assert answer["uncertain"] is True and answer["answered_by"] == "jev"


def test_a_local_only_request_never_reaches_jev(monkeypatch):
    configure(monkeypatch)
    asked = jev(monkeypatch, jev_answer("a", 0.99))
    answer, _ = run(FakeService(result(("area", unsure("a", 0.5, voters=VOTERS_ABC)))), request_json(local_only=True))
    assert asked == [] and answer["uncertain"] is True


def test_jev_switched_off_for_choice_is_never_asked(monkeypatch):
    flags = {v: {k: v != "jev" for k in decision.TRIAGE_TYPES} for v in decision.TRIAGE_VOTERS}
    configure(monkeypatch, triage_enabled=flags)
    asked = jev(monkeypatch, jev_answer("a", 0.99))
    run(FakeService(result(("area", unsure("a", 0.5, voters=VOTERS_ABC)))))
    assert asked == []


# --- the service is down ---------------------------------------------------------------------------------------

def test_with_the_service_down_jev_answers_alone(monkeypatch):
    configure(monkeypatch)
    asked = jev(monkeypatch, jev_answer("a", 0.95))
    usage = []
    service = FakeService(LayaServiceError("Laya could not read the complete input",
                                           [{"model": "convaiinnovations/laya", "input_tokens": None, "duration_ms": 3, "ok": False}]))
    answer, _ = run(service, on_usage=usage.append)
    assert asked == [["a", "b", "c"]] and answer["answered_by"] == "jev" and answer["uncertain"] is False
    assert usage[0]["ok"] is False and usage[0]["reason"] == "local_failed"


def test_with_the_service_down_and_no_fallback_the_error_says_why(monkeypatch):
    configure(monkeypatch, fallback=False)
    with pytest.raises(ValueError, match=r"no model could answer 'area' \(laya: The Laya service could not be reached"):
        run(FakeService(LayaServiceError("The Laya service could not be reached: down")))


def test_partial_results_mark_an_unanswered_question_instead_of_failing(monkeypatch):
    configure(monkeypatch, fallback=False)
    answer, _ = run(FakeService(LayaServiceError("down")), partial_results=True)
    assert answer["uncertain"] is True and answer["choice"] is None


def test_cancellation_stops_the_flow_before_the_service_is_asked(monkeypatch):
    configure(monkeypatch, fallback=False)
    service = FakeService(result(("area", choice("a", 0.9, uncertain=False))))

    def check():
        raise InterruptedError("cancelled")

    with pytest.raises(InterruptedError):
        TriageFlow(service=service, check=check).answer(request_json())
    assert not service.asked


# --- score and noul questions -------------------------------------------------------------------------------------

NOUL_REQUEST = json.dumps({"text": "t", "questions": {"area": {"type": "noul", "instructions": "Is it?"}}})


def noul_answer(value, confidence, uncertain):
    return {"type": "noul", "noul": value, "answer_confidence": confidence, "uncertain": uncertain, "answered_by": "laya-typed"}


def test_an_unsure_noul_question_goes_to_jev_and_is_flagged_by_the_two_option_threshold(monkeypatch):
    configure(monkeypatch)
    jev(monkeypatch, {"type": "noul", "noul": 0.9, "answer_confidence": 0.85, "uncertain": False, "answered_by": "jev"})
    answer, _ = run(FakeService(result(("area", noul_answer(0.6, 0.5, True)))), NOUL_REQUEST)
    assert answer["answered_by"] == "jev" and answer["uncertain"] is True  # 0.85 is under Jev's 0.90


def test_a_sure_noul_answer_from_the_service_stays_local(monkeypatch):
    configure(monkeypatch)
    asked = jev(monkeypatch)
    answer, _ = run(FakeService(result(("area", noul_answer(0.95, 0.95, False)))), NOUL_REQUEST)
    assert answer["answered_by"] == "laya-typed" and asked == []


def test_an_unsure_noul_question_without_the_fallback_keeps_the_local_answer(monkeypatch):
    configure(monkeypatch, fallback=False)
    answer, _ = run(FakeService(result(("area", noul_answer(0.6, 0.5, True)))), NOUL_REQUEST)
    assert answer["answered_by"] == "laya-typed" and answer["uncertain"] is True


# --- the hand-off ---------------------------------------------------------------------------------------------

def test_the_answer_is_compact_by_default_and_full_when_asked(monkeypatch):
    configure(monkeypatch, fallback=False)
    unknown = unsure("a", 0.5, voters=VOTERS_ABC, unknown=True, candidates=["a", "b"], also_check=["b"],
                     resolved_by="final", rounds=[{"step": "laya-english"}], note="n", disagreement={"laya-english": "a"})
    service = FakeService(result(("area", unknown)))
    compact, _ = run(service)
    assert list(compact) == ["type", "choice", "answer_confidence", "uncertain", "answered_by", "probabilities",
                             "also_check", "unknown", "candidates"]
    assert all(len(str(v)) <= 4 for v in compact["probabilities"].values())
    full, _ = run(service, request_json(trace=True))
    assert full["resolved_by"] == "final" and full["rounds"] and full["note"]
    configure(monkeypatch, fallback=False, triage_trace=True)
    assert "rounds" in run(service)[0]


def test_help_from_the_other_models_is_noted(monkeypatch):
    configure(monkeypatch, fallback=False)
    service = FakeService(result(("area", choice("a", 0.9, uncertain=False, by="laya-english+laya-typed"))))
    assert run(service)[1].model_note == "Settled with help from laya-typed."


def test_compact_keeps_what_the_caller_acts_on_for_every_question_type():
    unknown = {
        "type": "choice", "choice": "a", "probabilities": {"a": 0.51234, "b": 0.48766, "c": 0.0}, "answer_confidence": 0.51234,
        "uncertain": True, "answered_by": "laya-english+jev", "resolved_by": "final", "unknown": True, "candidates": ["a", "b"],
        "also_check": ["b"], "note": "x", "disagreement": {"laya-english": "a"}, "eliminated": ["c"], "rounds": [{}],
    }
    assert triage_flow.compact(unknown) == {
        "type": "choice", "choice": "a", "answer_confidence": 0.51, "uncertain": True, "answered_by": "laya-english+jev",
        "probabilities": {"a": 0.51, "b": 0.49, "c": 0.0}, "also_check": ["b"], "unknown": True, "candidates": ["a", "b"],
    }
    score = {"type": "score", "score": 1.94321, "legend": {"0": "x"}, "answer_confidence": 0.36111, "uncertain": True, "answered_by": "laya-english"}
    assert triage_flow.compact(score) == {"type": "score", "score": 1.94, "answer_confidence": 0.36, "uncertain": True, "answered_by": "laya-english"}
    noul = {"type": "noul", "noul": 0.9549, "answer_confidence": 0.9098, "uncertain": False, "answered_by": "laya-english", "resolved_by": "local"}
    assert triage_flow.compact(noul) == {"type": "noul", "noul": 0.95, "answer_confidence": 0.91, "uncertain": False, "answered_by": "laya-english"}


def test_run_chat_goes_through_the_flow(monkeypatch):
    configure(monkeypatch, fallback=False)
    service = FakeService(result(("area", choice("a", 0.9, uncertain=False))))
    monkeypatch.setattr(laya_model, "agent", lambda: service)
    import asyncio

    chat = asyncio.run(laya_provider.run_chat(request_json(), [], None, []))
    assert json.loads(chat.response)["answers"]["area"]["choice"] == "a" and service.asked[0]["strategy"] == "english-then-typed"


# --- the strategy -----------------------------------------------------------------------------------------

def two_questions(**extra):
    return json.dumps({"text": "t", "questions": {
        "area": {"type": "choice", "instructions": "Which?", "criteria": OPTIONS},
        "other": {"type": "choice", "instructions": "Which?", "criteria": OPTIONS},
    }, **extra})


def sure_pair():
    return result(("area", choice("a", 0.9, uncertain=False)), ("other", choice("a", 0.9, uncertain=False)))


def test_a_requested_strategy_replaces_the_voter_derived_one(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: None)
    service = FakeService(sure_pair())
    TriageFlow(service=service).answer(two_questions(strategy="consensus"))
    assert [(c["strategy"], list(c["questions"])) for c in service.asked] == [("consensus", ["area", "other"])]


def test_the_admin_default_applies_when_the_request_names_none(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: "typed-only")
    service = FakeService(sure_pair())
    TriageFlow(service=service).answer(two_questions())
    assert [c["strategy"] for c in service.asked] == ["typed-only"]


def test_the_request_beats_the_admin_default(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: "typed-only")
    service = FakeService(sure_pair())
    TriageFlow(service=service).answer(two_questions(strategy="average"))
    assert [c["strategy"] for c in service.asked] == ["average"]


def test_without_either_the_voters_choose(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: None)
    service = FakeService(sure_pair())
    TriageFlow(service=service).answer(two_questions())
    assert [c["strategy"] for c in service.asked] == ["english-then-typed"]


def test_an_unknown_strategy_is_refused_with_the_valid_names(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: None)
    service = FakeService(sure_pair(), strategy_names=("auto", "typed-only"))
    with pytest.raises(ValueError, match=r"Invalid Laya request: unknown strategy 'nope'; choose one of: auto, typed-only"):
        TriageFlow(service=service).answer(two_questions(strategy="nope"))
    assert service.asked == []


def test_a_service_that_cannot_list_strategies_still_gets_the_request(monkeypatch):
    configure(monkeypatch, fallback=False)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: None)
    service = FakeService(sure_pair())

    def down():
        raise LayaServiceError("down")

    service.strategies = down
    TriageFlow(service=service).answer(two_questions(strategy="consensus"))
    assert [c["strategy"] for c in service.asked] == ["consensus"]


@pytest.mark.parametrize("fallback", [False, True])
def test_a_strategy_refused_by_ask_is_invalid_even_when_listing_failed(monkeypatch, fallback):
    configure(monkeypatch, fallback=fallback)
    monkeypatch.setattr(triage_flow.tuning_overrides, "triage_strategy", lambda: None)
    service = FakeService(LayaServiceError("unknown strategy 'retired'", status=422))
    service.strategies = lambda: (_ for _ in ()).throw(LayaServiceError("down"))
    fallback_calls = jev(monkeypatch, jev_answer("a", 0.99), jev_answer("a", 0.99))
    with pytest.raises(ValueError, match="^Invalid Laya request: unknown strategy 'retired'"):
        TriageFlow(service=service).answer(two_questions(strategy="retired"))
    assert fallback_calls == []
