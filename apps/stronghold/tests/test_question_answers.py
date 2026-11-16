"""Clickable questions: the clamping and checking helpers, the turn's pending
question and snapshot, and (Task 4) the answer route."""

from __future__ import annotations

import asyncio


from src.turns import question_answers as qa

QUESTIONS = [
    {
        "header": "Format",
        "question": "Which format?",
        "multi_select": False,
        "options": [{"label": "CSV"}, {"label": "JSON", "description": "Structured"}],
    },
    {
        "header": "Extras",
        "question": "Which extras?",
        "multi_select": True,
        "options": [{"label": "Totals"}, {"label": "Chart"}, {"label": "Title"}],
    },
]


# --- clamp_questions -------------------------------------------------------------------


def test_clamp_keeps_a_good_request_as_it_is() -> None:
    assert qa.clamp_questions(QUESTIONS) == QUESTIONS


def test_clamp_cuts_long_text_and_extra_questions_and_options() -> None:
    raw = [
        {
            "header": "h" * 40,
            "question": "q" * 500,
            "multi_select": "truthy",
            "options": [{"label": "l" * 200, "description": "d" * 400}] + [{"label": f"o{i}"} for i in range(8)],
        }
    ] * 6

    clamped = qa.clamp_questions(raw)

    assert len(clamped) == qa.MAX_QUESTIONS
    first = clamped[0]
    assert len(first["header"]) == qa.HEADER_MAX and len(first["question"]) == qa.QUESTION_MAX
    assert first["multi_select"] is True
    assert len(first["options"]) == qa.MAX_OPTIONS
    assert len(first["options"][0]["label"]) == qa.LABEL_MAX
    assert len(first["options"][0]["description"]) == qa.DESCRIPTION_MAX


def test_clamp_drops_anything_that_is_not_a_question() -> None:
    assert qa.clamp_questions("nope") == []
    assert qa.clamp_questions([1, None, {"header": "x"}]) == []
    assert qa.clamp_questions([{"header": "x", "question": "y", "options": ["A", {"label": "B"}, {"nolabel": 1}]}]) == [
        {"header": "x", "question": "y", "multi_select": False, "options": [{"label": "B"}]}
    ]


# --- check_answers ---------------------------------------------------------------------


def ok(selected, other=None):
    return {"selected": selected, "other": other}


def test_a_complete_answer_passes() -> None:
    assert qa.check_answers(QUESTIONS, [ok(["CSV"]), ok(["Totals", "Chart"], "and a title")]) is None


def test_other_alone_is_an_answer() -> None:
    assert qa.check_answers(QUESTIONS, [ok([], "XML"), ok(["Title"])]) is None


def test_bad_answers_are_described() -> None:
    cases = {
        "too few answers": [ok(["CSV"])],
        "too many answers": [ok(["CSV"]), ok(["Chart"]), ok(["Title"])],
        "nothing chosen": [ok([]), ok(["Chart"])],
        "blank other only": [ok([], "   "), ok(["Chart"])],
        "an unknown label": [ok(["XML"]), ok(["Chart"])],
        "two for a single-select": [ok(["CSV", "JSON"]), ok(["Chart"])],
        "the same label twice": [ok(["CSV"]), ok(["Chart", "Chart"])],
    }
    for name, answers in cases.items():
        problem = qa.check_answers(QUESTIONS, answers)
        assert isinstance(problem, str) and problem, name
