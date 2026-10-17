"""scripts/check_triage_cases.py: the live triage cases are well formed and their report reads answers correctly."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts import check_triage_cases as cases
from src.llm import laya_provider


def test_every_case_is_a_valid_request_for_the_fallback_sized_window():
    for case in cases.CASES:
        request = laya_provider.parse_request(case.request(), 16_000)
        assert set(request.questions) == set(case.questions)
        assert set(case.expect) <= set(case.questions), case.name


def test_case_names_are_unique_and_each_says_what_it_is_for():
    names = [case.name for case in cases.CASES]
    assert len(names) == len(set(names)) and all(case.purpose for case in cases.CASES)


def test_the_cases_cover_every_path_the_setup_has():
    texts = {case.name: case for case in cases.CASES}
    assert len(texts["long-log"].text) > laya_provider.MAX_INPUT_CHARS
    assert {q["type"] for case in cases.CASES for q in case.questions.values()} == {"choice", "score", "noul"}
    assert any(len(q["criteria"]) >= 5 for case in cases.CASES for q in case.questions.values() if q["type"] == "choice")
    assert texts["checkout-area-lenient"].min_confidence == 0.5 and texts["clear-database-strict"].min_confidence == 0.95


@pytest.mark.parametrize("answer, path", [
    ({"choice": "a"}, "laya"),
    ({"choice": "a", "answered_by": "jev"}, "fallback"),
    ({"choice": "a", "answered_by": "laya+jev"}, "blend"),
    ({"choice": "a", "answered_by": "jev", "deferred_to": "jev"}, "deferred->jev"),
    ({"choice": "a", "answered_by": "laya", "deferred_to": "laya"}, "deferred->laya"),
    ({"choice": "a", "answered_by": "jev", "eliminated": ["c"]}, "narrowed->jev"),
    ({"choice": "a", "answered_by": "laya", "eliminated": ["c"]}, "narrowed->laya"),
])
def test_the_path_says_how_a_question_was_settled(answer, path):
    assert cases.path_of(answer) == path


def test_expectations_read_choices_and_noul_answers():
    assert cases.matches({"type": "choice", "choice": "database"}, "database")
    assert not cases.matches({"type": "choice", "choice": "network"}, "database")
    assert cases.matches({"type": "noul", "noul": 0.9}, "true") and cases.matches({"type": "noul", "noul": 0.1}, "false")
    assert not cases.matches({"type": "noul", "noul": 0.9}, "false")


class FakeLaya:
    def __init__(self, answers, tokens=100):
        self.answers, self.tokens, self.requests = answers, tokens, []

    def answer(self, raw):
        self.requests.append(json.loads(raw))
        return SimpleNamespace(response=json.dumps({"answers": self.answers}), input_tokens=self.tokens)


def test_a_case_becomes_one_row_per_question_with_its_expectation_checked():
    answers = {
        "category": {"type": "choice", "choice": "database", "answer_confidence": 0.91, "uncertain": False},
        "needs_investigation": {"type": "noul", "noul": 0.2, "answer_confidence": 0.8, "uncertain": False,
                                "answered_by": "jev"},
    }
    case = next(c for c in cases.CASES if c.name == "full-triage")

    rows, error = cases.run_case(FakeLaya(answers), case)

    assert error == "" and [r.question for r in rows] == ["category", "needs_investigation"]
    assert rows[0].ok is True and rows[0].path == "laya" and rows[0].tokens == 100
    assert rows[1].ok is False and rows[1].path == "fallback" and rows[1].got == "0.20"


def test_a_failing_case_is_reported_not_raised():
    class Broken:
        def answer(self, raw):
            raise ValueError("Laya could not read the complete input")

    rows, error = cases.run_case(Broken(), cases.CASES[0])

    assert rows == [] and error == "ValueError: Laya could not read the complete input"


def test_the_summary_counts_expectations_paths_and_tokens_once_per_case():
    answers = {"category": {"type": "choice", "choice": "database", "answer_confidence": 0.9, "uncertain": False}}
    rows, _ = cases.run_case(FakeLaya(answers, tokens=120), cases.CASES[0])
    text = cases.summary(rows, {})

    assert "correct 1/1" in text and "laya 1" in text and "input tokens 120" in text
    assert "case" in cases.table(rows).splitlines()[0] and "clear-database" in cases.table(rows)


def test_selecting_cases_by_name_and_refusing_unknown_ones():
    assert [c.name for c in cases.select(["vague", "clear-network"])] == ["vague", "clear-network"]
    assert len(cases.select([])) == len(cases.CASES)
    with pytest.raises(SystemExit, match="unknown case"):
        cases.select(["nope"])


def test_list_prints_each_case_and_runs_nothing(capsys):
    assert cases.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert all(case.name in out for case in cases.CASES)
