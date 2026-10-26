"""Shared decision questions and model size tiers."""

SIZE_CRITERIA = {
    "tiny": "a lookup, a rename, a one-line answer",
    "everyday": "a normal email, post, or short document",
    "large": "a multi-step build, research, a full report",
    "hardest": "strategy, or anything where a wrong call is expensive",
}
SIZE_QUESTION = "How big is this request?"
DEFAULT_SIZE_TIERS = (("tiny", "light"), ("everyday", "light"), ("large", "standard"), ("hardest", "heavy"))

NONE = "none"


def choice_question(instructions: str, criteria: dict[str, str]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}
