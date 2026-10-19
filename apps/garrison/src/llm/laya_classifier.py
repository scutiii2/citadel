"""Decision backend `laya`: the local Laya model answering one `choice` question.

Free and private, but its window is 512 tokens: a text or option list that does not
fit is a ClassifierError, so a chain such as ["laya", "jev"] hands those to the
next backend. Not in the default chains; add it in config_tuning.json's
`classifier.chains`. See llm/decision.py.
"""

from __future__ import annotations

import json
from typing import Mapping

from src.llm import laya_provider
from src.llm.decision import Choice, ClassifierError

ID = "laya"
_QUESTION_ID = "answer"


def available() -> bool:
    return laya_provider.is_available()


def ask_choice(subject: str, criteria: Mapping[str, str], question: str, timeout: float) -> Choice:
    """`timeout` is not enforced: the model runs in this process."""
    raw = json.dumps({"text": subject, "questions": {_QUESTION_ID: {"type": "choice", "instructions": question, "criteria": dict(criteria)}}})
    try:
        request = laya_provider.parse_request(raw)
        answers, tokens = laya_provider.answer_typed(request)
    except (ValueError, RuntimeError) as error:  # too long, too many options, not installed, bad result
        raise ClassifierError(f"Laya could not answer: {error}") from error
    answer = answers[_QUESTION_ID]
    return Choice(
        answer["choice"], round(answer["answer_confidence"] * 100), tokens, ID, laya_provider.DEFAULT_MODEL,
        dict(answer["probabilities"]),
    )
