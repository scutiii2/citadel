"""The Triage Assistant (llm/laya_provider.py) with classifier.triage_flow set to "sequential": the settings, the
hand-off to llm/triage_flow.py, the second checkpoint and the window it reads."""

from __future__ import annotations

import asyncio
import copy
import json

import pytest

from src.llm import decision, laya_provider
from src.llm.laya_provider import LayaQuestions

OPTIONS = {"a": "A", "b": "B", "c": "C"}


def request_json(options=OPTIONS):
    return json.dumps({"text": "some text", "questions": {"area": {"type": "choice", "instructions": "Which?", "criteria": options}}})


def prediction(probabilities, confidence, tokens=10):
    return {
        "answers": {"area": {"choice": max(probabilities, key=probabilities.get), "probabilities": probabilities, "answer_confidence": confidence}},
        "usage": {"input_tokens": tokens, "output_tokens": 0, "state_tokens": 5, "truncated": False},
    }


class Engine:
    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def predict(self, state, questions, **kwargs):
        self.calls.append({"options": list(questions["area"]["criteria"]), **kwargs})
        return copy.deepcopy(self.results.pop(0))


def sequential(monkeypatch, **changes):
    config = decision.ClassifierSettings(triage_flow="sequential", **changes)
    monkeypatch.setattr(decision, "settings", lambda: config)
    return config


def questions(english, typed):
    return LayaQuestions(english, typed=LayaQuestions(typed))


# --- the settings ------------------------------------------------------------------------------------------

def use_section(monkeypatch, section):
    decision.reset_cache()
    monkeypatch.setattr(decision, "read_section", lambda path, name, default=None: section)


def test_the_legacy_flow_is_the_default(monkeypatch):
    use_section(monkeypatch, {})
    config = decision.settings()
    assert (config.triage_flow, config.triage_window, config.triage_thresholds) == ("legacy", 4096, {})
    assert config.triage_trace is False


def test_the_flow_window_and_thresholds_are_read(monkeypatch):
    use_section(monkeypatch, {
        "triage_flow": "sequential", "triage_window": 2048, "triage_trace": True,
        "triage_thresholds": {"2": {"laya-typed": 0.85}, "3+": {"jev": 0.8, "laya-english": 0.7}},
    })
    config = decision.settings()
    assert config.triage_flow == "sequential" and config.triage_window == 2048 and config.triage_trace is True
    assert config.triage_thresholds == {"2": {"laya-typed": 0.85}, "3+": {"jev": 0.8, "laya-english": 0.7}}


@pytest.mark.parametrize("section", [
    {"triage_flow": "parallel"}, {"triage_flow": 1}, {"triage_window": 100}, {"triage_window": 99999}, {"triage_window": True},
    {"triage_window": "big"}, {"triage_thresholds": []}, {"triage_thresholds": {"4": {"jev": 0.9}}},
    {"triage_thresholds": {"2": []}}, {"triage_thresholds": {"2": {"gpt": 0.9}}}, {"triage_thresholds": {"2": {"jev": 0}}},
    {"triage_thresholds": {"2": {"jev": 1.5}}}, {"triage_thresholds": {"2": {"jev": True}}},
])
def test_a_bad_flow_setting_is_refused(monkeypatch, section):
    use_section(monkeypatch, section)
    with pytest.raises(ValueError, match="classifier"):
        decision.settings()
    decision.reset_cache()


# --- the hand-off ---------------------------------------------------------------------------------------------

def test_a_sure_english_answer_is_returned_as_a_chat_result_and_typed_is_never_loaded(monkeypatch):
    sequential(monkeypatch)
    english = Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.8))
    typed = Engine()
    provider = questions(english, typed)

    result = provider.answer(request_json())
    body = json.loads(result.response)

    assert body["answers"]["area"]["choice"] == "a" and body["answers"]["area"]["answered_by"] == "laya-english"
    assert body["uncertain"] is False and "rounds" not in body["answers"]["area"]
    assert (result.provider_id, result.model, result.input_tokens, result.output_tokens) == ("laya", "convaiinnovations/laya", 10, 0)
    assert result.model_note == "" and typed.calls == []


def test_both_checkpoints_read_the_configured_window(monkeypatch):
    sequential(monkeypatch, triage_window=3000)
    english = Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5))
    typed = Engine(prediction({"a": 0.4, "b": 0.3, "c": 0.3}, 0.5))

    questions(english, typed).answer(request_json())

    assert english.calls[0]["max_len"] == 3000 and typed.calls[0]["max_len"] == 3000


def test_the_legacy_flow_still_reads_the_old_window_and_never_touches_typed(monkeypatch):
    monkeypatch.setattr(decision, "settings", decision.ClassifierSettings)
    english = Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.8))
    typed = Engine()

    questions(english, typed).answer(request_json())

    assert english.calls[0]["max_len"] == laya_provider.CONTEXT_WINDOW and typed.calls == []


def test_help_from_the_other_models_is_noted_and_an_unsure_answer_flags_the_result(monkeypatch):
    sequential(monkeypatch, triage_trace=True)  # the fallback stays off: only the two Laya models vote
    english = Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5))
    typed = Engine(prediction({"a": 0.3, "b": 0.4, "c": 0.3}, 0.5))

    result = questions(english, typed).answer(request_json())
    body = json.loads(result.response)

    assert body["answers"]["area"]["answered_by"] == "laya-english+laya-typed" and body["answers"]["area"]["resolved_by"] == "final"
    assert body["uncertain"] is True and result.model_note == "Settled with help from laya-typed."
    assert result.input_tokens == 20 and [r["step"] for r in body["answers"]["area"]["rounds"]][:2] == ["laya-english", "laya-typed"]


def test_the_configured_thresholds_reach_the_flow(monkeypatch):
    sequential(monkeypatch, triage_thresholds={"3+": {"laya-english": 0.95}})
    english = Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.8))
    typed = Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.8))

    result = questions(english, typed).answer(request_json())

    # 0.8 met the default 0.75 but not the configured 0.95; typed (0.55) agrees and takes it.
    assert json.loads(result.response)["answers"]["area"]["answered_by"] == "laya-english+laya-typed"


def test_the_fallback_is_asked_only_when_the_flow_switches_it_on(monkeypatch):
    monkeypatch.setattr(decision, "available", lambda *a, **k: True)
    asked = []

    def ask(request, qids):
        asked.append(qids)
        return {qids[0]: {"type": "choice", "choice": "a", "probabilities": {"a": 0.95, "b": 0.03, "c": 0.02},
                          "answer_confidence": 0.93, "uncertain": False, "answered_by": "jev"}}, 5, []

    monkeypatch.setattr(laya_provider, "_ask_fallback", ask)
    unsure = lambda: (Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5)), Engine(prediction({"a": 0.3, "b": 0.4, "c": 0.3}, 0.5)))

    sequential(monkeypatch)
    questions(*unsure()).answer(request_json())
    assert asked == []

    sequential(monkeypatch, triage_fallback=True, triage_trace=True)
    result = questions(*unsure()).answer(request_json())
    body = json.loads(result.response)["answers"]["area"]
    assert asked == [["area"]] and body["answered_by"] == "jev" and body["resolved_by"] == "jev"
    assert result.input_tokens == 25 and result.model_note == "Settled with help from jev."


def test_run_chat_goes_through_the_flow(monkeypatch):
    sequential(monkeypatch)
    english = Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.8))
    monkeypatch.setattr(laya_provider, "_questions", questions(english, Engine()))

    result = asyncio.run(laya_provider.run_chat(request_json(), [], None, []))

    assert json.loads(result.response)["answers"]["area"]["answered_by"] == "laya-english"


# --- preparing the agent -----------------------------------------------------------------------------------------

def test_prepare_loads_the_typed_checkpoint_only_for_the_sequential_flow(monkeypatch):
    loaded = []

    class Loading(LayaQuestions):
        def _load(self):
            loaded.append(self._checkpoint)
            return self._engine or object()

    monkeypatch.setattr(decision, "settings", decision.ClassifierSettings)
    Loading().prepare()
    assert loaded == ["convaiinnovations/laya"]

    loaded.clear()
    sequential(monkeypatch)
    provider = Loading()
    provider._typed = Loading(checkpoint="typed-decisions")
    provider.prepare()
    assert loaded == ["convaiinnovations/laya", "typed-decisions"]
    assert provider._typed._typed is None  # warming the typed model must not build yet another one


def test_the_typed_model_is_the_typed_decisions_checkpoint_on_the_flow_window(monkeypatch):
    sequential(monkeypatch, triage_window=2048)
    provider = LayaQuestions(Engine())

    models = provider._flow_models()

    assert list(models) == ["laya-english", "laya-typed"] and models["laya-english"] is provider
    assert models["laya-typed"]._checkpoint == "typed-decisions" == laya_provider.TYPED_MODEL
    assert provider.window == models["laya-typed"].window == 2048


# --- the compact answer ---------------------------------------------------------------------------------------------

def reviewed(monkeypatch, request=None, **changes):
    """A question the two Laya models cannot settle, so its full answer is long."""
    sequential(monkeypatch, **changes)
    english = Engine(prediction({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5))
    typed = Engine(prediction({"a": 0.3, "b": 0.4, "c": 0.3}, 0.5))
    return questions(english, typed).answer(request or request_json())


def test_the_answer_is_compact_by_default(monkeypatch):
    result = reviewed(monkeypatch)
    answer = json.loads(result.response)["answers"]["area"]

    # These two models could not settle it, so the answer is "unknown" and says which options to look at.
    assert list(answer) == [
        "type", "choice", "answer_confidence", "uncertain", "answered_by", "probabilities", "also_check", "unknown", "candidates",
    ]
    assert answer["answered_by"] == "laya-english+laya-typed" and answer["also_check"] and answer["unknown"] is True
    assert all(len(str(v)) <= 4 for v in answer["probabilities"].values())  # two decimals
    for dropped in ("rounds", "resolved_by", "disagreement", "note", "eliminated"):
        assert dropped not in answer
    assert reviewed_size(monkeypatch, trace=True) > 3 * reviewed_size(monkeypatch, trace=False)


def reviewed_size(monkeypatch, trace):
    return len(reviewed(monkeypatch, triage_trace=trace).response)


def test_a_request_can_ask_for_the_full_answer(monkeypatch):
    raw = json.dumps({**json.loads(request_json()), "trace": True})
    answer = json.loads(reviewed(monkeypatch, raw).response)["answers"]["area"]

    assert answer["resolved_by"] == "final" and answer["rounds"][0]["step"] == "laya-english" and answer["note"]


def test_the_config_can_ask_for_the_full_answer_for_every_request(monkeypatch):
    answer = json.loads(reviewed(monkeypatch, triage_trace=True).response)["answers"]["area"]
    assert "rounds" in answer and "resolved_by" in answer


def test_trace_must_be_true_or_false():
    raw = json.dumps({**json.loads(request_json()), "trace": "yes"})
    with pytest.raises(ValueError, match="trace must be true or false"):
        laya_provider.parse_request(raw)
    assert laya_provider.parse_request(request_json()).trace is False
    assert laya_provider.parse_request(json.dumps({**json.loads(request_json()), "trace": True})).trace is True


def test_the_legacy_flow_ignores_trace_and_keeps_its_answer(monkeypatch):
    monkeypatch.setattr(decision, "settings", decision.ClassifierSettings)
    raw = json.dumps({**json.loads(request_json()), "trace": True})

    result = questions(Engine(prediction({"a": 0.9, "b": 0.05, "c": 0.05}, 0.8)), Engine()).answer(raw)

    assert json.loads(result.response)["answers"]["area"]["uncertain"] is False


def test_compact_keeps_what_the_caller_acts_on_for_every_question_type():
    from src.llm import triage_flow

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
