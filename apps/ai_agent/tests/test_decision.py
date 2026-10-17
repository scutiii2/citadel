"""The decision layer: settings, backend chains and the Laya backend."""

from __future__ import annotations

import json

import pytest

from src.llm import decision, laya_classifier, laya_provider
from src.llm.decision import Choice, ClassifierError, ClassifierSettings

CRITERIA = {"database": "SQL and storage", "network": "Connections"}


@pytest.fixture(autouse=True)
def fresh_settings():
    decision.reset_cache()
    yield
    decision.reset_cache()


def use_section(monkeypatch, section):
    monkeypatch.setattr(decision, "read_section", lambda path, name, default=None: section)


class FakeBackend:
    """A stand-in for a backend module."""

    def __init__(self, ident, *, up=True, outcome=None):
        self.ID, self.up, self.outcome, self.calls = ident, up, outcome, []

    def available(self):
        return self.up

    def ask_choice(self, subject, criteria, question, timeout):
        self.calls.append((subject, question, timeout))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def backends(monkeypatch, **fakes):
    monkeypatch.setattr(decision, "_backend", lambda ident: fakes[ident])
    return fakes


def chain(monkeypatch, *ids):
    use_section(monkeypatch, {"chains": {"auto_route": list(ids)}})


# --- settings ---------------------------------------------------------------------------------

def test_everything_is_off_by_default(monkeypatch):
    use_section(monkeypatch, {})
    config = decision.settings()
    assert config == ClassifierSettings() and config.triage_fallback is False
    assert config.chain("triage") == ("jev", "jev_vercel")
    assert config.typesafe.url == "https://api.typesafe.ai/v1/systemone" and config.typesafe.model == "jev-latest"
    assert config.vercel.model == "typesafe-ai/jev"


def test_settings_read_the_section_over_the_defaults(monkeypatch):
    use_section(monkeypatch, {
        "triage_fallback": True, "timeout_seconds": 5, "max_input_chars": 9000,
        "typesafe": {"model": "jev-preview"}, "vercel": {"url": "https://gw.example/v1"},
        "chains": {"triage": ["laya", "jev"], "auto_tier": ["jev_vercel"]},
    })
    config = decision.settings()
    assert (config.triage_fallback, config.timeout_seconds, config.max_input_chars) == (True, 5.0, 9000)
    assert (config.typesafe.model, config.typesafe.url) == ("jev-preview", "https://api.typesafe.ai/v1/systemone")
    assert config.vercel.url == "https://gw.example/v1" and config.vercel.model == "typesafe-ai/jev"
    assert config.chain("triage") == ("laya", "jev") and config.chain("auto_tier") == ("jev_vercel",)
    assert config.chain("auto_route") == ("jev", "jev_vercel")


def test_the_confidence_gap_defaults_to_0_3_and_can_be_changed(monkeypatch):
    use_section(monkeypatch, {})
    assert decision.settings().triage_confidence_gap == 0.3
    decision.reset_cache()
    use_section(monkeypatch, {"triage_confidence_gap": 0.5})
    assert decision.settings().triage_confidence_gap == 0.5


def test_the_prune_ratio_defaults_to_a_quarter_and_can_be_changed_or_switched_off(monkeypatch):
    use_section(monkeypatch, {})
    assert decision.settings().triage_prune_ratio == 0.25
    for given, expected in ((0, 0.0), (0.4, 0.4)):
        decision.reset_cache()
        use_section(monkeypatch, {"triage_prune_ratio": given})
        assert decision.settings().triage_prune_ratio == expected


@pytest.mark.parametrize("section", [
    [], {"nope": 1}, {"triage_fallback": "yes"}, {"timeout_seconds": 0}, {"timeout_seconds": True},
    {"max_input_chars": 0}, {"typesafe": []}, {"typesafe": {"nope": 1}}, {"typesafe": {"url": ""}}, {"vercel": {"model": 3}},
    {"chains": []}, {"chains": {"nothing": ["jev"]}}, {"chains": {"triage": []}}, {"chains": {"triage": ["gpt"]}},
    {"chains": {"triage": ["jev", "jev"]}}, {"chains": {"triage": "jev"}},
    {"triage_prune_ratio": 1}, {"triage_prune_ratio": -0.1}, {"triage_prune_ratio": True}, {"triage_prune_ratio": "x"},
    {"triage_confidence_gap": 0}, {"triage_confidence_gap": 1.5}, {"triage_confidence_gap": True}, {"triage_confidence_gap": "x"},
])
def test_a_bad_section_is_refused(monkeypatch, section):
    use_section(monkeypatch, section)
    with pytest.raises(ValueError, match="classifier"):
        decision.settings()


# --- the chain --------------------------------------------------------------------------------

def test_the_first_available_backend_answers(monkeypatch):
    chain(monkeypatch, "jev", "jev_vercel")
    fakes = backends(
        monkeypatch, jev=FakeBackend("jev", up=False), jev_vercel=FakeBackend("jev_vercel", outcome=Choice("network", 80, 5, "jev_vercel")),
    )

    picked = decision.ask_choice("text", CRITERIA, "Which?", "auto_route")

    assert picked.backend == "jev_vercel" and fakes["jev"].calls == []
    assert fakes["jev_vercel"].calls == [("text", "Which?", 3.0)]


def test_a_failing_backend_hands_over_to_the_next(monkeypatch):
    chain(monkeypatch, "jev", "jev_vercel")
    fakes = backends(
        monkeypatch, jev=FakeBackend("jev", outcome=ClassifierError("down")),
        jev_vercel=FakeBackend("jev_vercel", outcome=Choice("database", 70, 5, "jev_vercel")),
    )

    assert decision.ask_choice("t", CRITERIA, "q", "auto_route").choice == "database"
    assert len(fakes["jev"].calls) == 1


def test_every_backend_failing_raises_the_last_error(monkeypatch):
    chain(monkeypatch, "jev", "jev_vercel")
    backends(monkeypatch, jev=FakeBackend("jev", outcome=ClassifierError("a")), jev_vercel=FakeBackend("jev_vercel", outcome=ClassifierError("b")))

    with pytest.raises(ClassifierError, match="b"):
        decision.ask_choice("t", CRITERIA, "q", "auto_route")


def test_no_available_backend_is_a_classifier_error(monkeypatch):
    chain(monkeypatch, "jev")
    backends(monkeypatch, jev=FakeBackend("jev", up=False))

    assert decision.available("auto_route") is False
    with pytest.raises(ClassifierError, match="no classifier backend is available for auto_route"):
        decision.ask_choice("t", CRITERIA, "q", "auto_route")


def test_a_less_sure_answer_goes_on_to_the_next_backend_and_the_last_one_is_returned(monkeypatch):
    chain(monkeypatch, "laya", "jev")
    fakes = backends(
        monkeypatch, laya=FakeBackend("laya", outcome=Choice("network", 40, 5, "laya")),
        jev=FakeBackend("jev", outcome=Choice("database", 90, 5, "jev")),
    )

    assert decision.ask_choice("t", CRITERIA, "q", "auto_route", min_confidence=60).backend == "jev"
    fakes["jev"].outcome = Choice("database", 50, 5, "jev")
    assert decision.ask_choice("t", CRITERIA, "q", "auto_route", min_confidence=60).confidence == 50


def test_a_sure_first_answer_stops_the_chain_and_no_threshold_never_escalates(monkeypatch):
    chain(monkeypatch, "laya", "jev")
    fakes = backends(
        monkeypatch, laya=FakeBackend("laya", outcome=Choice("network", 65, 5, "laya")),
        jev=FakeBackend("jev", outcome=Choice("database", 99, 5, "jev")),
    )

    assert decision.ask_choice("t", CRITERIA, "q", "auto_route", min_confidence=60).backend == "laya"
    assert decision.ask_choice("t", CRITERIA, "q", "auto_route").backend == "laya"
    assert fakes["jev"].calls == []


def test_excluded_backends_are_skipped_and_the_timeout_is_passed_on(monkeypatch):
    chain(monkeypatch, "laya", "jev")
    fakes = backends(monkeypatch, laya=FakeBackend("laya", outcome=Choice("network", 99, 5, "laya")), jev=FakeBackend("jev", outcome=Choice("database", 90, 5, "jev")))

    picked = decision.ask_choice("t", CRITERIA, "q", "auto_route", exclude=("laya",), timeout=7.5)

    assert picked.backend == "jev" and fakes["laya"].calls == [] and fakes["jev"].calls[0][2] == 7.5


def test_a_choice_needs_two_options_and_a_known_feature(monkeypatch):
    with pytest.raises(ClassifierError, match="two options"):
        decision.ask_choice("t", {"only": "one"}, "q", "auto_route")
    with pytest.raises(ValueError, match="unknown classifier feature"):
        decision.ask_choice("t", CRITERIA, "q", "other")


def test_classify_size_uses_the_auto_tier_chain_and_its_threshold(monkeypatch):
    use_section(monkeypatch, {"chains": {"auto_tier": ["laya", "jev"]}, "auto_tier": {"min_confidence": 70}})
    fakes = backends(
        monkeypatch, laya=FakeBackend("laya", outcome=Choice("tiny", 50, 5, "laya")),
        jev=FakeBackend("jev", outcome=Choice("large", 88, 5, "jev")),
    )

    picked = decision.classify_size("build me a report")

    assert picked.choice == "large"
    assert fakes["jev"].calls[0][1] == decision.SIZE_QUESTION


def test_post_json_turns_every_failure_into_a_classifier_error(monkeypatch):
    import urllib.error

    def boom(request, timeout):
        raise urllib.error.HTTPError("u", 429, "slow down", {}, None)

    monkeypatch.setattr(decision.urllib.request, "urlopen", boom)
    with pytest.raises(ClassifierError, match="TypeSafe answered HTTP 429"):
        decision.post_json("https://x", {}, "k", 1.0, "TypeSafe")

    def unreachable(request, timeout):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(decision.urllib.request, "urlopen", unreachable)
    with pytest.raises(ClassifierError, match="could not be reached"):
        decision.post_json("https://x", {}, "k", 1.0, "the gateway")


# --- the Laya backend -------------------------------------------------------------------------

def fake_laya(monkeypatch, *, answer=None, error=None):
    sent = []

    def answer_typed(request):
        sent.append(request)
        if error:
            raise error
        return {"answer": answer}, 77

    monkeypatch.setattr(laya_provider, "answer_typed", answer_typed)
    return sent


def test_laya_answers_one_choice_question(monkeypatch):
    sent = fake_laya(monkeypatch, answer={
        "type": "choice", "choice": "network", "answer_confidence": 0.82, "probabilities": {"database": 0.18, "network": 0.82},
    })

    picked = laya_classifier.ask_choice("connection reset", CRITERIA, "Which area?", 3.0)

    assert picked == Choice("network", 82, 77, "laya", laya_provider.DEFAULT_MODEL, {"database": 0.18, "network": 0.82})
    assert sent[0].text == "connection reset" and sent[0].questions["answer"]["criteria"] == CRITERIA
    assert sent[0].questions["answer"]["instructions"] == "Which area?"


@pytest.mark.parametrize("make", [
    lambda: ("x" * 4001, CRITERIA),                       # too long for Laya
    lambda: ("text", {str(i): f"option {i}" for i in range(11)}),  # too many options
])
def test_laya_hands_over_what_does_not_fit(monkeypatch, make):
    fake_laya(monkeypatch, answer={})
    subject, criteria = make()
    with pytest.raises(ClassifierError, match="Laya could not answer"):
        laya_classifier.ask_choice(subject, criteria, "Which?", 3.0)


def test_laya_that_cannot_read_the_whole_text_is_a_classifier_error(monkeypatch):
    fake_laya(monkeypatch, error=laya_provider._InputTooLong("too long"))
    with pytest.raises(ClassifierError, match="too long"):
        laya_classifier.ask_choice("text", CRITERIA, "Which?", 3.0)
    fake_laya(monkeypatch, error=RuntimeError("Laya is not installed"))
    with pytest.raises(ClassifierError, match="not installed"):
        laya_classifier.ask_choice("text", CRITERIA, "Which?", 3.0)


def test_the_request_laya_gets_is_valid_json_for_its_parser():
    json.loads(json.dumps({"text": "t", "questions": {"answer": {"type": "choice", "instructions": "q", "criteria": CRITERIA}}}))
    assert laya_provider.parse_request(json.dumps(
        {"text": "t", "questions": {"answer": {"type": "choice", "instructions": "q", "criteria": CRITERIA}}}
    )).questions["answer"]["type"] == "choice"
