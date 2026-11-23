import pytest

from src.gateway.decision.answers import answer_from, compact, default_threshold, mark

CHOICE = {"type": "choice", "instructions": "x", "criteria": {"a": "A", "b": "B", "c": "C"}}
SCORE = {"type": "score", "instructions": "x", "criteria": ["low", "mid", "high"]}
NOUL = {"type": "noul", "instructions": "x"}
BOX = {"type": "box", "instructions": "x"}


def test_choice():
    raw = {"type": "choice", "choice": "a", "confidence": 0.7, "probabilities": {"a": 0.7, "b": 0.2, "c": 0.1}}
    assert answer_from(CHOICE, raw) == {"type": "choice", "choice": "a", "answer_confidence": 0.7,
                                        "probabilities": {"a": 0.7, "b": 0.2, "c": 0.1}}


def test_choice_unknown_option_or_keys_fail():
    with pytest.raises(ValueError):
        answer_from(CHOICE, {"choice": "z", "confidence": 0.7, "probabilities": {"a": 0.7, "b": 0.2, "c": 0.1}})
    with pytest.raises(ValueError):
        answer_from(CHOICE, {"choice": "a", "confidence": 0.7, "probabilities": {"a": 1.0}})


def test_score():
    raw = {"score": 1.5, "confidence": 0.55, "probabilities": {"0": 0.1, "1": 0.5, "2": 0.4}}
    out = answer_from(SCORE, raw)
    assert out["score"] == 1.5 and out["answer_confidence"] == 0.55
    assert out["legend"] == {"0": "low", "1": "mid", "2": "high"}
    with pytest.raises(ValueError):
        answer_from(SCORE, {"score": 3, "confidence": 0.5})


def test_noul_confidence_is_the_stronger_side():
    assert answer_from(NOUL, {"noul": 0.98}) == {"type": "noul", "noul": 0.98, "answer_confidence": 0.98}
    assert answer_from(NOUL, {"noul": 0.1})["answer_confidence"] == 0.9
    with pytest.raises(ValueError):
        answer_from(NOUL, {"noul": 1.4})


def test_box_with_and_without_confidence():
    raw = {"box": {"top": 0.2, "bottom": 0.66, "left": 0.19, "right": 0.68}, "confidence": None}
    out = answer_from(BOX, raw)
    assert out == {"type": "box", "box": raw["box"], "answer_confidence": None}
    assert answer_from(BOX, {**raw, "confidence": 0.8})["answer_confidence"] == 0.8
    with pytest.raises(ValueError):
        answer_from(BOX, {"box": {"top": 0.7, "bottom": 0.2, "left": 0.1, "right": 0.5}})
    with pytest.raises(ValueError):
        answer_from(BOX, {"box": {"top": 0.1, "bottom": 0.2, "left": 0.1}})


def test_mark_uncertain():
    a = {"answer_confidence": 0.8}
    mark(a, CHOICE, None, 0.9)
    assert a["uncertain"] is True
    mark(a, CHOICE, 0.7, 0.9)
    assert a["uncertain"] is False
    mark(a, CHOICE, None, None)
    assert a["uncertain"] is False


def test_mark_box_without_confidence():
    a = {"answer_confidence": None}
    mark(a, BOX, None, None)
    assert a["uncertain"] is False
    mark(a, BOX, 0.5, None)
    assert a["uncertain"] is True


def test_default_threshold():
    assert default_threshold({"type": "choice", "criteria": {"a": "", "b": ""}}) == 0.9
    assert default_threshold(CHOICE) == 0.75
    assert default_threshold(NOUL) == 0.9 and default_threshold(BOX) is None


def test_compact_drops_trace_keys():
    assert compact({"choice": "a", "rounds": 2, "voters": {}, "options": []}) == {"choice": "a"}
