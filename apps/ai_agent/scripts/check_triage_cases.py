"""Live test cases for the Triage Assistant's classifier setup (Laya, then the decision layer's fallback).

Run from ai_agent:
    python -m scripts.check_triage_cases                 # every case with your config_tuning.json
    python -m scripts.check_triage_cases --list          # what each case is for
    python -m scripts.check_triage_cases --case checkout-area --case clear-database
    python -m scripts.check_triage_cases --baseline      # the same cases with the fallback off (Laya alone)
    python -m scripts.check_triage_cases --prune-ratio 0.4 --json

It calls the same code the Triage Assistant runs (LayaQuestions.answer), so the orchestrator is not
involved. It loads the local Laya model, reads the `classifier` section of configs/config_tuning.json and
the keys in .env, and sends each case's text to the fallback backend when the section turns it on (a few
cents of tokens in all). Each row shows how a question was settled:

    laya       Laya was sure; nothing left the machine
    fallback   the classifier answered alone (text too long for Laya, or Laya had no usable answer)
    blend      Laya and the classifier were averaged, nothing dropped
    narrowed   options far below the rest were dropped and the question asked again (then who decided)

Expected choices are a smoke check, not a benchmark: a case with no expectation is for watching the
paths and numbers. Exit code 1 with --strict when a case with an expectation got a different answer.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

PROJECT = Path(__file__).resolve().parents[1]

CATEGORY = {
    "type": "choice",
    "instructions": "Which category best describes this technical issue?",
    "criteria": {
        "database": "Database queries, storage, SQL, locking or data integrity errors.",
        "network": "Connections, DNS, timeouts, sockets or unreachable services.",
        "authentication": "Login, identity, credentials, authorization or access denied.",
        "configuration": "Missing or incorrect settings, environment variables or setup.",
        "unknown": "No technical issue, insufficient evidence, or none of these categories fits.",
    },
}
SEVERITY = {
    "type": "choice",
    "instructions": "How severe is the issue described? Do not assume unstated impact.",
    "criteria": {
        "informational": "Normal operation or an informational event without a problem.",
        "warning": "An error or degraded operation without evidence of a critical incident.",
        "critical": "An explicit service outage, data loss, security breach or complete failure.",
    },
}
NEEDS_INVESTIGATION = {
    "type": "noul",
    "instructions": "Does this text describe a technical problem that needs investigation?",
    "criteria": {"false": "Normal operation; no technical problem.", "true": "A failure or problem needs investigation."},
}
AREA = {
    "type": "choice",
    "instructions": "Which area is affected",
    "criteria": {"billing": "payments", "frontend": "web UI", "network": "connections"},
}
IMPACT = {
    "type": "score",
    "instructions": "How many users are affected?",
    "criteria": ["nobody", "a few users", "many users", "nearly everyone"],
}
URGENT = {"type": "noul", "instructions": "The message needs action today"}


@dataclass(frozen=True)
class Case:
    name: str
    purpose: str
    text: str
    questions: dict[str, dict[str, Any]]
    # question id -> expected choice ("true"/"false" for a noul question); empty = just observe
    expect: dict[str, str] = field(default_factory=dict)
    min_confidence: float | None = None

    def request(self) -> str:
        body: dict[str, Any] = {"text": self.text, "questions": self.questions}
        if self.min_confidence is not None:
            body["min_confidence"] = self.min_confidence
        return json.dumps(body)


_LOG_NOISE = "INFO health check ok\n" * 300  # about 6000 characters: more than Laya reads

CASES = [
    Case("clear-database", "Laya is sure: no fallback, nothing leaves the machine.",
         "SQLite database is locked; the SQL write failed.", {"category": CATEGORY}, {"category": "database"}),
    Case("clear-network", "Laya is sure about a different category.",
         "Connection refused when opening a socket to the service.", {"category": CATEGORY}, {"category": "network"}),
    Case("clear-auth", "Laya is sure about a third category.",
         "Login failed: invalid username or password.", {"category": CATEGORY}, {"category": "authentication"}),
    Case("small-talk", "No technical issue: should land on `unknown`.",
         "Hello, good morning!", {"category": CATEGORY}, {"category": "unknown"}),
    Case("vague", "Almost no evidence: Laya is unsure, so the fallback weighs in.",
         "Something feels off lately.", {"category": CATEGORY}),
    Case("checkout-area", "The known disagreement case: Laya says frontend, Jev says billing.",
         "The checkout page times out for about half of users since this morning.", {"area": AREA}),
    Case("checkout-area-lenient", "The same text with min_confidence 0.5: fewer questions go to the fallback.",
         "The checkout page times out for about half of users since this morning.", {"area": AREA}, min_confidence=0.5),
    Case("clear-database-strict", "A clear text with min_confidence 0.95: forces the fallback even for an easy one.",
         "SQLite database is locked; the SQL write failed.", {"category": CATEGORY}, {"category": "database"}, 0.95),
    Case("mixed-signals", "Two plausible areas in one sentence.",
         "Users report slow pages and the payment provider shows delayed settlements.", {"area": AREA}),
    Case("two-causes", "Five options, two real causes: watch which options get dropped.",
         "After the deploy the app cannot reach the database server and logins also fail.", {"category": CATEGORY}),
    Case("wrong-total", "Five options and a vague symptom: a good case for narrowing.",
         "The checkout form submits but the order total is wrong and sometimes nothing happens.", {"category": CATEGORY}),
    Case("severity-outage", "A choice question with a clear top option.",
         "The whole site is down and customers cannot place orders; some data may be lost.", {"severity": SEVERITY},
         {"severity": "critical"}),
    Case("severity-info", "The opposite end of the same question.",
         "The nightly job finished in 4 minutes, as usual.", {"severity": SEVERITY}, {"severity": "informational"}),
    Case("impact-score", "A score question: the fallback answers it as a level, with no narrowing.",
         "About half of users cannot check out.", {"impact": IMPACT}),
    Case("urgent-noul", "A noul question: the fallback answers it as true or false, with no narrowing.",
         "Please look at this when you have time next week.", {"urgent": URGENT}, {"urgent": "false"}),
    Case("full-triage", "Three questions at once, as the Triage Assistant's own example schema.",
         "SQLite database is locked; the SQL write failed.",
         {"category": CATEGORY, "severity": SEVERITY, "needs_investigation": NEEDS_INVESTIGATION},
         {"category": "database", "needs_investigation": "true"}),
    Case("long-log", "Over Laya's 4000 characters: only the fallback can read it.",
         _LOG_NOISE + "ERROR could not connect to database server: connection refused\n", {"category": CATEGORY}),
]


def load_env() -> None:
    """Put .env into the environment (it never overrides what is already set), as agent_config does."""
    for key, value in dotenv_values(PROJECT / ".env").items():
        if value:
            os.environ.setdefault(key, value)


def path_of(answer: dict[str, Any]) -> str:
    """How one answer was settled; see the module docstring."""
    by = answer.get("answered_by")
    if by is None:
        return "laya"
    if "eliminated" in answer:
        return f"narrowed->{by}"
    if "+" in by:
        return "blend"
    return "fallback"


def matches(answer: dict[str, Any], expected: str) -> bool:
    if answer["type"] == "noul":
        return (answer["noul"] >= 0.5) == (expected == "true")
    return answer.get("choice") == expected


def picked(answer: dict[str, Any]) -> str:
    if answer["type"] == "noul":
        return f"{answer['noul']:.2f}"
    if answer["type"] == "score":
        return f"{answer['score']:.2f}"
    return str(answer["choice"])


@dataclass
class Row:
    case: str
    question: str
    expected: str
    got: str
    ok: bool | None
    path: str
    rounds: int
    confidence: float
    uncertain: bool
    tokens: int
    seconds: float
    answer: dict[str, Any]


def run_case(laya: Any, case: Case) -> tuple[list[Row], str]:
    """Ask Laya's provider code directly. Returns one row per question and an error text ('' on success)."""
    started = time.perf_counter()
    try:
        result = laya.answer(case.request())
    except Exception as error:  # noqa: BLE001 - reported per case so one failure does not hide the rest
        return [], f"{type(error).__name__}: {error}"
    seconds = time.perf_counter() - started
    answers = json.loads(result.response)["answers"]
    rows = []
    for qid, answer in answers.items():
        expected = case.expect.get(qid, "")
        rows.append(Row(
            case.name, qid, expected, picked(answer), matches(answer, expected) if expected else None, path_of(answer),
            len(answer.get("rounds", ())), answer["answer_confidence"], answer["uncertain"],
            result.input_tokens, seconds, answer,
        ))
    return rows, ""


def table(rows: list[Row]) -> str:
    head = ("case", "question", "expect", "got", "ok", "path", "rounds", "conf", "unsure", "tokens", "secs")
    body = [
        (r.case, r.question, r.expected or "-", r.got, {True: "yes", False: "NO", None: "-"}[r.ok], r.path,
         str(r.rounds or "-"), f"{r.confidence:.2f}", "yes" if r.uncertain else "no", str(r.tokens), f"{r.seconds:.1f}")
        for r in rows
    ]
    widths = [max(len(line[i]) for line in [head, *body]) for i in range(len(head))]
    lines = ["  ".join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip() for line in [head, *body]]
    return "\n".join(lines)


def summary(rows: list[Row], errors: dict[str, str]) -> str:
    judged = [r for r in rows if r.ok is not None]
    paths: dict[str, int] = {}
    for row in rows:
        key = row.path.split("->")[0]
        paths[key] = paths.get(key, 0) + 1
    # Tokens are per request, so count each case once.
    tokens = {r.case: r.tokens for r in rows}
    return "\n".join([
        f"correct {sum(bool(r.ok) for r in judged)}/{len(judged)} with an expectation, "
        f"{len(rows)} answers from {len(tokens)} cases, {len(errors)} failed",
        "paths: " + ", ".join(f"{name} {count}" for name, count in sorted(paths.items())),
        f"input tokens {sum(tokens.values())}, unsure answers {sum(r.uncertain for r in rows)}, "
        f"time {sum({r.case: r.seconds for r in rows}.values()):.1f}s",
    ])


def select(names: list[str]) -> list[Case]:
    if not names:
        return list(CASES)
    known = {case.name: case for case in CASES}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise SystemExit(f"unknown case(s): {', '.join(unknown)}. Use --list to see them.")
    return [known[name] for name in names]


def apply_settings(baseline: bool, prune_ratio: float | None) -> None:
    from src.llm import decision

    config = decision.ClassifierSettings() if baseline else decision.settings()
    if prune_ratio is not None:
        config = dataclasses.replace(config, triage_prune_ratio=prune_ratio)
    decision.settings = lambda: config  # type: ignore[assignment]
    print(
        f"classifier: triage_fallback={config.triage_fallback}, chain={'+'.join(config.chain('triage'))}, "
        f"prune_ratio={config.triage_prune_ratio}", flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="list the cases and what each is for")
    parser.add_argument("--case", action="append", default=[], metavar="NAME", help="run only this case (repeatable)")
    parser.add_argument("--baseline", action="store_true", help="ignore config_tuning.json: Laya alone, no fallback")
    parser.add_argument("--prune-ratio", type=float, metavar="R", help="override classifier.triage_prune_ratio")
    parser.add_argument("--json", action="store_true", help="also print each answer in full (with its rounds trace)")
    parser.add_argument("--strict", action="store_true", help="exit 1 when an expectation is missed or a case fails")
    args = parser.parse_args(argv)

    if args.list:
        width = max(len(case.name) for case in CASES)
        for case in CASES:
            print(f"{case.name.ljust(width)}  {case.purpose}")
        return 0

    cases = select(args.case)
    load_env()
    sys.path.insert(0, str(PROJECT))
    apply_settings(args.baseline, args.prune_ratio)
    from src.llm.laya_provider import LayaQuestions

    laya = LayaQuestions()
    print("loading Laya (the first run may download weights)...", flush=True)
    laya.prepare()
    rows: list[Row] = []
    errors: dict[str, str] = {}
    for case in cases:
        new, error = run_case(laya, case)
        rows += new
        if error:
            errors[case.name] = error
        if args.json:
            for row in new:
                print(json.dumps({"case": row.case, "question": row.question, "answer": row.answer}, ensure_ascii=False))
    print(table(rows))
    for name, error in errors.items():
        print(f"FAILED {name}: {error}")
    print(summary(rows, errors))
    missed = any(r.ok is False for r in rows)
    return 1 if args.strict and (missed or errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
