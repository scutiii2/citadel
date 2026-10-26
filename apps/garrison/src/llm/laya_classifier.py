"""Decision backend `laya`: the Laya service answering one `choice` question with its English model.

Free and private, but its window is 512 tokens: a text or option list that does not
fit is a ClassifierError, so a chain such as ["laya", "jev"] hands those to the
next backend. Not in the default chains; add it in config_tuning.json's
`classifier.chains`. See llm/decision.py.
"""

from __future__ import annotations

import json
from typing import Mapping

from src.llm import laya_model, laya_provider
from src.llm.decision import Choice, ClassifierError

ID = "laya"
_QUESTION_ID = "answer"


def available() -> bool:
    return laya_provider.is_available()


def ask_choice(subject: str, criteria: Mapping[str, str], question: str, timeout: float) -> Choice:
    """`timeout` is not enforced: the Laya service has its own."""
    raw = json.dumps({"text": subject, "questions": {_QUESTION_ID: {"type": "choice", "instructions": question, "criteria": dict(criteria)}}})
    try:
        request = laya_provider.parse_request(raw)
        result = laya_model.agent().ask("english-only", request.text, request.questions, laya_provider.CONTEXT_WINDOW)
    except (ValueError, RuntimeError) as error:  # too long, too many options, service down, bad result
        raise ClassifierError(f"Laya could not answer: {error}") from error
    answer = result["answers"][_QUESTION_ID]
    tokens = sum(call["input_tokens"] or 0 for call in result["calls"])
    return Choice(
        answer["choice"], round(answer["answer_confidence"] * 100), tokens, ID, laya_provider.DEFAULT_MODEL,
        dict(answer["probabilities"]),
    )
