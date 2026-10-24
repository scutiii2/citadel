"""The decision layer: settings, backend chains and the Laya backend."""

from __future__ import annotations

import json

import pytest

from types import SimpleNamespace

from src.llm import decision, laya_agent, laya_classifier, laya_provider
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


def test_the_pair_ratio_defaults_to_a_half_and_can_be_changed(monkeypatch):
    use_section(monkeypatch, {})
    assert decision.settings().triage_pair_ratio == 0.5
    decision.reset_cache()
    use_section(monkeypatch, {"triage_pair_ratio": 0.25})
    assert decision.settings().triage_pair_ratio == 0.25


def test_settings_of_the_removed_legacy_flow_are_ignored(monkeypatch):
    use_section(monkeypatch, {"triage_flow": "sequential", "triage_confidence_gap": 0.5})
    assert decision.settings() == ClassifierSettings()


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
    {"triage_trace": "yes"}, {"triage_trace": 1},
    {"triage_pair_ratio": 0}, {"triage_pair_ratio": 1.5}, {"triage_pair_ratio": True}, {"triage_pair_ratio": "x"},
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

    class Service:
        def ask(self, strategy, text, questions, max_len, **tuning):
            sent.append(SimpleNamespace(strategy=strategy, text=text, questions=questions))
            if error:
                raise error
            return {"answers": {"answer": answer}, "calls": [{"input_tokens": 77}]}

    monkeypatch.setattr(laya_agent, "agent", lambda: Service())
    return sent


def test_laya_answers_one_choice_question(monkeypatch):
    sent = fake_laya(monkeypatch, answer={
        "type": "choice", "choice": "network", "answer_confidence": 0.82, "probabilities": {"database": 0.18, "network": 0.82},
    })

    picked = laya_classifier.ask_choice("connection reset", CRITERIA, "Which area?", 3.0)

    assert picked == Choice("network", 82, 77, "laya", laya_provider.DEFAULT_MODEL, {"database": 0.18, "network": 0.82})
    assert sent[0].strategy == "english-only"
    assert sent[0].text == "connection reset" and sent[0].questions["answer"]["criteria"] == CRITERIA
    assert sent[0].questions["answer"]["instructions"] == "Which area?"


def test_laya_hands_over_a_text_that_does_not_fit(monkeypatch):
    fake_laya(monkeypatch, answer={})
    with pytest.raises(ClassifierError, match="Laya could not answer"):
        laya_classifier.ask_choice("x" * 4001, CRITERIA, "Which?", 3.0)


def test_laya_hands_over_options_the_service_refuses(monkeypatch):
    fake_laya(monkeypatch, error=laya_agent.LayaServiceError("question 'answer' (choice) criteria must be an object of 2 to 10", status=422))
    with pytest.raises(ClassifierError, match="Laya could not answer"):
        laya_classifier.ask_choice("text", {str(i): f"option {i}" for i in range(11)}, "Which?", 3.0)


def test_laya_that_cannot_read_the_whole_text_is_a_classifier_error(monkeypatch):
    fake_laya(monkeypatch, error=laya_agent.LayaServiceError("too long"))
    with pytest.raises(ClassifierError, match="too long"):
        laya_classifier.ask_choice("text", CRITERIA, "Which?", 3.0)
    fake_laya(monkeypatch, error=laya_agent.LayaServiceError("Laya is not configured"))
    with pytest.raises(ClassifierError, match="not configured"):
        laya_classifier.ask_choice("text", CRITERIA, "Which?", 3.0)


def test_the_request_laya_gets_is_valid_json_for_its_parser():
    json.loads(json.dumps({"text": "t", "questions": {"answer": {"type": "choice", "instructions": "q", "criteria": CRITERIA}}}))
    assert laya_provider.parse_request(json.dumps(
        {"text": "t", "questions": {"answer": {"type": "choice", "instructions": "q", "criteria": CRITERIA}}}
    )).questions["answer"]["type"] == "choice"


# --- the shipped examples ------------------------------------------------------------------------------------

def test_the_example_config_seeds_every_classifier_key_at_its_default(monkeypatch):
    import dataclasses
    import json
    from pathlib import Path

    from src.llm import triage_flow

    path = Path(decision.__file__).resolve().parents[2] / "configs" / "config_tuning.json.example"
    use_section(monkeypatch, json.loads(path.read_text(encoding="utf-8"))["classifier"])

    seeded = decision.settings()

    assert seeded.triage_thresholds == triage_flow.DEFAULT_THRESHOLDS
    assert all(seeded.chain(feature) == ClassifierSettings().chain(feature) for feature in decision.FEATURES)
    # nothing switched on, nothing off the default (the chains and thresholds were compared above)
    assert dataclasses.replace(seeded, triage_thresholds={}, chains={}) == ClassifierSettings()
    assert seeded.triage_fallback is False
    assert seeded.auto_tier.enabled is False and seeded.auto_route.enabled is False


def test_the_example_config_names_active_classifier_settings_only():
    import json
    from pathlib import Path

    path = Path(decision.__file__).resolve().parents[2] / "configs" / "config_tuning.json.example"
    legacy_routing = {"auto_route", "auto_tier"}
    example_keys = set(json.loads(path.read_text(encoding="utf-8"))["classifier"])
    assert legacy_routing <= decision._KNOWN  # Old deployments remain readable.
    assert example_keys == decision._KNOWN - legacy_routing


def test_the_example_env_lists_the_keys_the_classifier_backends_read():
    from pathlib import Path

    from src.llm import jev_classifier, typesafe_classifier

    text = (Path(decision.__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    keys = {line.split("=")[0] for line in text.splitlines() if "=" in line and not line.startswith("#")}
    assert {typesafe_classifier.KEY_ENV, jev_classifier.KEY_ENV, "HF_TOKEN"} <= keys


# --- triage_enabled / triage_order -------------------------------------------------------------------------

def test_every_model_answers_every_type_by_default_except_english_for_noul(monkeypatch):
    use_section(monkeypatch, {})
    config = decision.settings()
    assert config.voters("choice") == ("laya-english", "laya-typed", "jev")
    assert config.voters("score") == ("laya-english", "laya-typed", "jev")
    assert config.voters("noul") == ("laya-typed", "jev")


def test_triage_enabled_switches_a_model_off_for_one_type(monkeypatch):
    use_section(monkeypatch, {"triage_enabled": {"laya-english": {"choice": False}, "jev": {"score": False}}})
    config = decision.settings()
    assert config.voters("choice") == ("laya-typed", "jev")
    assert config.voters("score") == ("laya-english", "laya-typed")


def test_triage_order_arranges_the_models_of_a_type(monkeypatch):
    use_section(monkeypatch, {"triage_order": {"noul": ["jev", "laya-typed"], "score": ["laya-typed"]}})
    config = decision.settings()
    assert config.voters("noul") == ("jev", "laya-typed") and config.voters("score") == ("laya-typed",)
    assert config.voters("choice") == ("laya-english", "laya-typed", "jev")  # untouched types keep their order


@pytest.mark.parametrize("section", [
    {"triage_enabled": []}, {"triage_enabled": {"gpt": {"choice": True}}}, {"triage_enabled": {"jev": []}},
    {"triage_enabled": {"jev": {"multi": True}}}, {"triage_enabled": {"jev": {"choice": "yes"}}},
    {"triage_order": []}, {"triage_order": {"multi": ["jev"]}}, {"triage_order": {"noul": []}},
    {"triage_order": {"noul": "jev"}}, {"triage_order": {"noul": ["gpt"]}}, {"triage_order": {"noul": ["jev", "jev"]}},
    {"triage_order": {"choice": ["jev", "laya-typed"]}},  # the fallback is the last resort of a choice question
    {"triage_enabled": {"laya-typed": {"noul": False}, "jev": {"noul": False}}},  # nobody left to answer noul
    {"triage_order": {"score": ["jev"]}, "triage_enabled": {"jev": {"score": False}}},
])
def test_a_bad_voter_setting_is_refused(monkeypatch, section):
    use_section(monkeypatch, section)
    with pytest.raises(ValueError):
        decision.settings()
