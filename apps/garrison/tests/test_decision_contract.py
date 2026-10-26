from src.providers.decision import contract, questions


def test_request_defaults():
    request = contract.DecisionRequest("hello", {"q": questions.choice_question("Which?", {"a": "A", "b": "B"})})
    assert request.min_confidence == 0.9 and request.local_only is False
    assert request.questions["q"] == {"type": "choice", "instructions": "Which?", "criteria": {"a": "A", "b": "B"}}


def test_size_constants_cover_four_sizes():
    assert set(questions.SIZE_CRITERIA) == {"tiny", "everyday", "large", "hardest"}
    assert dict(questions.DEFAULT_SIZE_TIERS)["hardest"] == "heavy"
