"""scripts/check_triage_cases.py: the live triage cases are well formed and their report reads answers correctly."""

from __future__ import annotations

import dataclasses
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
    ({"choice": "a", "answered_by": "laya+jev", "resolved_by": "pair"}, "pair"),
    ({"choice": "a", "answered_by": "laya+jev", "resolved_by": "pair", "eliminated": ["c"]}, "narrowed->pair"),
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


# --- the rounds tables ---------------------------------------------------------------------------

CHECKOUT = {
    "type": "choice", "choice": "billing", "probabilities": {"billing": 0.69, "frontend": 0.31, "network": 0.0},
    "answer_confidence": 0.38, "uncertain": True, "answered_by": "jev", "eliminated": ["network"],
    "rounds": [
        {"step": "laya", "choice": "frontend", "probabilities": {"billing": 0.2439, "frontend": 0.6642, "network": 0.0919}, "confidence": 0.6642},
        {"step": "jev", "choice": "billing", "probabilities": {"billing": 0.71, "frontend": 0.26, "network": 0.03}, "confidence": 0.56},
        {"step": "average", "probabilities": {"billing": 0.4769, "frontend": 0.4621, "network": 0.0609}, "eliminated": ["network"]},
        {"step": "laya", "choice": "frontend", "probabilities": {"billing": 0.3005, "frontend": 0.6995}, "confidence": 0.6995,
         "options": ["billing", "frontend"]},
        {"step": "jev", "choice": "billing", "probabilities": {"billing": 0.69, "frontend": 0.31}, "confidence": 0.38,
         "options": ["billing", "frontend"]},
    ],
}


def checkout_row(answer=CHECKOUT, **changes):
    row = cases.Row("checkout-area", "area", "", "billing", None, "narrowed->jev", 5, 0.38, True, 724, 1.2, answer)
    return dataclasses.replace(row, **changes)


def test_the_rounds_table_lists_every_call_with_a_column_per_option():
    lines = cases.rounds_table(checkout_row()).splitlines()

    assert lines[0] == "checkout-area / area: expected -, got billing"
    header, rule, *body = [line for line in lines if line.startswith("|")]
    assert [c.strip() for c in header.strip("|").split("|")] == [
        "#", "Step", "Options", "Pick", "Billing", "Frontend", "Network", "Confidence",
    ]
    assert set(rule.replace("|", "").replace(" ", "")) == {"-"}
    cells = [[c.strip() for c in line.strip("|").split("|")] for line in body]
    assert cells[0] == ["1", "Laya", "all 3", "frontend", "0.2439", "0.6642", "0.0919", "0.6642"]
    assert cells[1] == ["2", "Jev", "all 3", "billing", "0.71", "0.26", "0.03", "0.56"]
    assert cells[2] == ["3", "Average", "all 3", "", "0.4769", "0.4621", "0.0609", ""]
    assert cells[3] == ["4", "Laya, narrowed", "billing, frontend", "frontend", "0.3005", "0.6995", "-", "0.6995"]
    assert cells[4] == ["5", "Jev, narrowed", "billing, frontend", "billing", "0.69", "0.31", "-", "0.38"]
    assert lines[-2] == "final: billing (billing 0.69, frontend 0.31, network 0); answered by jev; unsure: yes"
    assert lines[-1] == "dropped: network"
    assert "also check" not in "\n".join(lines)  # no pair rule ran in this answer


def test_the_rounds_table_names_the_option_to_also_check():
    pair = {**CHECKOUT, "resolved_by": "pair", "also_check": ["frontend"]}
    assert cases.rounds_table(checkout_row(pair)).splitlines()[-1] == "also check: frontend"


def test_the_rounds_table_shows_a_deferral_and_a_failed_rerun():
    deferred = {
        "type": "choice", "choice": "unknown", "probabilities": {"auth": 0.0, "unknown": 1.0}, "answer_confidence": 1.0,
        "uncertain": False, "answered_by": "jev", "deferred_to": "jev",
        "rounds": [
            {"step": "laya", "choice": "unknown", "probabilities": {"auth": 0.5, "unknown": 0.5}, "confidence": 0.3},
            {"step": "jev", "choice": "unknown", "probabilities": {"auth": 0.0, "unknown": 1.0}, "confidence": 1.0},
            {"step": "gap", "gap": 0.7, "deferred_to": "jev"},
        ],
    }
    text = cases.rounds_table(checkout_row(deferred, got="unknown", uncertain=False))
    assert "| 3 | Gap  |" in text and "defers to Jev" in text and "0.7" in text and "dropped" not in text

    failed = {**CHECKOUT, "rounds": [*CHECKOUT["rounds"][:3], {"step": "laya", "options": ["billing", "frontend"], "failed": "gone"}]}
    assert "failed: gone" in cases.rounds_table(checkout_row(failed))


def test_an_answer_without_a_second_opinion_has_no_rounds_table():
    plain = {k: v for k, v in CHECKOUT.items() if k != "rounds"}
    assert cases.rounds_table(checkout_row(plain)) == ""


def test_rounds_flag_prints_the_tables_after_the_summary_table(monkeypatch, capsys):
    from src.llm import decision

    monkeypatch.setattr(cases, "load_env", lambda: None)
    monkeypatch.setattr(decision, "settings", decision.ClassifierSettings)
    monkeypatch.setattr(laya_provider.LayaQuestions, "prepare", lambda self: None)
    answers = {"category": CHECKOUT}
    monkeypatch.setattr(laya_provider.LayaQuestions, "answer", lambda self, raw: FakeLaya(answers).answer(raw))

    assert cases.main(["--case", "vague", "--rounds"]) == 0
    out = capsys.readouterr().out

    assert out.index("case") < out.index("| # | Step") and "dropped: network" in out


# --- the wider case set -----------------------------------------------------------------------------

def test_the_wider_set_reaches_every_shape_the_triage_setup_handles():
    by_name = {case.name: case for case in cases.CASES}
    questions = [q for case in cases.CASES for q in case.questions.values()]
    # two-option choice questions (the pair rule), a ten-option one (Laya's maximum) and an eight-question request
    assert any(q["type"] == "choice" and len(q["criteria"]) == 2 for q in questions)
    assert any(q["type"] == "choice" and len(q["criteria"]) == laya_provider.MAX_OPTIONS for q in questions)
    assert max(len(case.questions) for case in cases.CASES) == laya_provider.MAX_QUESTIONS
    # text shapes: Laya's window overflow, the issue first or last, another language, an instruction hidden in the text
    assert 1000 < len(by_name["medium-text"].text) < laya_provider.MAX_INPUT_CHARS
    assert len(by_name["long-key-first"].text) > laya_provider.MAX_INPUT_CHARS
    assert by_name["long-key-first"].text.startswith("SQLite database is locked")
    assert by_name["medium-text"].text.rstrip().endswith("write failed.")
    assert "Ignore all previous instructions" in by_name["instruction-in-text"].text
    assert "base de datos" in by_name["non-english"].text
    # thresholds: the same text under a lenient and a strict min_confidence for a two-option and a three-option question
    assert by_name["escalate-lenient"].min_confidence == 0.5 and by_name["escalate-strict"].min_confidence == 0.95
    assert by_name["checkout-area-strict"].min_confidence == 0.95


def test_every_expectation_names_an_option_or_a_noul_answer_the_question_offers():
    for case in cases.CASES:
        for qid, expected in case.expect.items():
            question = case.questions[qid]
            allowed = {"true", "false"} if question["type"] == "noul" else set(question.get("criteria", ()))
            assert expected in allowed, (case.name, qid, expected)
            assert question["type"] != "score", (case.name, "score answers cannot be matched against a choice")


def test_case_patterns_select_a_group_in_listing_order():
    assert [c.name for c in cases.select(["escalate-*"])] == [
        "escalate-clear", "escalate-routine", "escalate-borderline", "escalate-conflicting", "escalate-lenient", "escalate-strict",
    ]
    assert [c.name for c in cases.select(["urgent-*", "vague"])][-1] == "vague"
    assert [c.name for c in cases.select(["vague", "vague"])] == ["vague"]
    with pytest.raises(SystemExit, match="unknown case.*nothing-\\*"):
        cases.select(["nothing-*"])
