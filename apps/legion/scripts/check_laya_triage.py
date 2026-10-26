"""Small real-model smoke evaluation, not an accuracy or calibration benchmark.

Run from ai_agent: python -m scripts.check_laya_triage
Asks the Laya service only (LAYA_SERVICE_URL); never calls a cloud LLM or changes agent configuration.
Sends the triage example schema below through the same provider path agents use.
"""

import json

from scripts.check_triage_cases import CATEGORY, NEEDS_INVESTIGATION, SEVERITY
from src.providers.decision import provider

TRIAGE_QUESTIONS = {"category": CATEGORY, "severity": SEVERITY, "needs_investigation": NEEDS_INVESTIGATION}

CASES = [
    ("SQLite database is locked; the SQL write failed.", "database"),
    ("PostgreSQL rejected the SQL query due to a syntax error.", "database"),
    ("Connection refused when opening a socket to the service.", "network"),
    ("DNS lookup failed; the hostname could not be resolved.", "network"),
    ("Login failed: invalid username or password.", "authentication"),
    ("Access denied: the account lacks permission to view this page.", "authentication"),
    ("Application startup failed: required configuration setting is missing.", "configuration"),
    ("The server port configuration has an invalid value.", "configuration"),
    ("The scheduled backup completed successfully. Everything is operating normally.", "unknown"),
    ("Hello, good morning!", "unknown"),
]


def main() -> None:
    correct = 0
    uncertain = 0
    for text, expected in CASES:
        result = provider.answer(json.dumps({"text": text, "questions": TRIAGE_QUESTIONS}), "laya-only", .9)
        data = json.loads(result.response)
        category = data["answers"]["category"]["choice"]
        correct += category == expected
        is_uncertain = any(answer["uncertain"] for answer in data["answers"].values())
        uncertain += is_uncertain
        print(json.dumps({"input": text, "expected": expected, "category": category,
                          "uncertain": is_uncertain, "answers": data["answers"]}, ensure_ascii=True), flush=True)
    print(json.dumps({"category_matches": correct, "examples": len(CASES),
                      "uncertain": uncertain, "note": "Smoke examples only; thresholds are not calibrated."}), flush=True)


if __name__ == "__main__":
    main()
