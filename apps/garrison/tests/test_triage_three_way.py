"""scripts/triage_three_way.py and `check_triage_cases --three-way`: the flags and the rounds table. The flow itself
is tested in test_triage_flow.py."""

from __future__ import annotations

import json

import pytest

from scripts import check_triage_cases as cases
from scripts import triage_three_way as three
from src.providers.decision import decision


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
