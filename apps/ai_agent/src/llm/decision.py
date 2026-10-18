"""Decision layer: ask a small classifier model "which option fits, and how sure".

One interface, several backends. A backend is a module in this package with
`ID`, `available()` and `ask_choice(subject, criteria, question, timeout)`:

| id           | module                 | what it is                                          |
|--------------|------------------------|-----------------------------------------------------|
| `jev`        | typesafe_classifier    | TypeSafe's own Jev API (real probabilities)         |
| `jev_vercel` | jev_classifier         | Jev through Vercel AI Gateway (self-reported 0-100) |
| `laya`       | laya_classifier        | the local Laya model (512-token window)             |

A feature (`triage`, `auto_tier`, `auto_route`) names a chain of backends in
config_tuning.json's `classifier.chains`. The chain is walked in order: a backend
without a key, one that fails, or (when the caller gives `min_confidence`) one that
is not confident enough hands over to the next. The last answer is returned, so the
caller still applies its own threshold. No usable answer raises ClassifierError,
which a caller treats as "no answer" and carries on without.

All off by default. A feature runs only when its section in `classifier` turns it
on and a backend of its chain is available. Text sent to a remote backend leaves
this machine, and each call is billed by that backend.
"""

from __future__ import annotations

import importlib
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Mapping

from src.core.catalog import catalog
from src.core.config_files import TUNING_PATH, read_section

_log = logging.getLogger(__name__)

_SECTION = "classifier"
FEATURES = ("triage", "auto_tier", "auto_route")
# The voters of the triage flow (llm/triage_flow.py) and the option counts their thresholds are set for.
TRIAGE_VOTERS = ("laya-english", "laya-typed", "jev")
TRIAGE_COUNTS = ("2", "3+")
# The question types a Laya request can hold, the voters tried for each in order, and which voters may answer which.
TRIAGE_TYPES = ("choice", "noul", "score")
# A noul question skips English: its true/false labels can override the text (a confident "no" on clearly positive input).
DEFAULT_TRIAGE_ORDER = {
    "choice": TRIAGE_VOTERS, "noul": ("laya-typed", "jev"), "score": TRIAGE_VOTERS,
}
DEFAULT_TRIAGE_ENABLED = {voter: {kind: True for kind in TRIAGE_TYPES} for voter in TRIAGE_VOTERS}
DEFAULT_CHAIN = ("jev", "jev_vercel")
_BACKENDS = {
    "jev": "src.llm.typesafe_classifier",
    "jev_vercel": "src.llm.jev_classifier",
    "laya": "src.llm.laya_classifier",
}
_KNOWN = {"typesafe", "vercel", "chains", "timeout_seconds", "max_input_chars", "triage_fallback", "triage_trace", "triage_window", "triage_thresholds", "triage_enabled", "triage_order", "triage_prune_ratio",
          "triage_pair_ratio", "auto_tier", "auto_route"}
# Settings of the removed legacy triage flow: still read from an old config_tuning.json, and ignored.
_RETIRED = {"triage_flow", "triage_confidence_gap"}
_BACKEND_KNOWN = {"url", "model"}
_AUTO_TIER_KNOWN = {"enabled", "min_confidence", "tiers"}
_AUTO_ROUTE_KNOWN = {"enabled", "min_confidence"}

# How hard a request is, as the ClaudeRouters size classifier names it.
SIZE_CRITERIA = {
    "tiny": "a lookup, a rename, a one-line answer",
    "everyday": "a normal email, post, or short document",
    "large": "a multi-step build, research, a full report",
    "hardest": "strategy, or anything where a wrong call is expensive",
}
SIZE_QUESTION = "How big is this request?"
DEFAULT_SIZE_TIERS = (("tiny", "light"), ("everyday", "light"), ("large", "standard"), ("hardest", "heavy"))


class ClassifierError(Exception):
    """No backend gave a usable answer; the message says why."""


@dataclass(frozen=True)
class Choice:
    choice: str
    confidence: int  # 0-100; each backend's own measure, not a calibrated probability
    prompt_tokens: int
    backend: str = ""  # the backend id that answered
    model: str = ""
    # Option -> probability when the backend reports a distribution (summing to about 1), else None.
    probabilities: dict[str, float] | None = None


@dataclass(frozen=True)
class BackendSettings:
    url: str
    model: str


@dataclass(frozen=True)
class AutoTierSettings:
    """Choosing a turn's model tier from how hard the question looks (llm/auto_tier.py)."""

    enabled: bool = False
    # Confidence (0-100) needed before the size is used; below it the default model runs.
    min_confidence: int = 60
    # request size -> model tier; the agent's own min_tier/max_tier still clamp the result.
    tiers: tuple[tuple[str, str], ...] = DEFAULT_SIZE_TIERS


@dataclass(frozen=True)
class AutoRouteSettings:
    """Sending a question straight to a specialist, without the orchestrator's own model call
    (agents/auto_route.py)."""

    enabled: bool = False
    # Confidence (0-100) needed before a specialist is picked; below it the orchestrator answers.
    min_confidence: int = 60


@dataclass(frozen=True)
class ClassifierSettings:
    typesafe: BackendSettings = BackendSettings("https://api.typesafe.ai/v1/systemone", "jev-latest")
    vercel: BackendSettings = BackendSettings("https://ai-gateway.vercel.sh/v1/chat/completions", "typesafe-ai/jev")
    # feature -> backend ids in the order they are tried; a feature not listed uses DEFAULT_CHAIN.
    chains: dict[str, tuple[str, ...]] = field(default_factory=dict)
    timeout_seconds: float = 3.0
    # Longest text sent for a typed question. Laya reads at most 4000 characters;
    # a remote backend has a larger window, so longer texts go to it instead.
    max_input_chars: int = 16_000
    # Re-ask a remote backend about the answers Laya is unsure of, and about texts Laya cannot read.
    triage_fallback: bool = False
    # The triage flow returns the full answer, with its rounds trace, instead of the compact one
    # (a request can ask for it with "trace": true).
    triage_trace: bool = False
    # Token window both Laya checkpoints read (llm/triage_flow.py).
    triage_window: int = 4096
    # count ("2" or "3+") -> voter -> the confidence (0-1) at which that voter's answer is taken, over the defaults in
    # llm/triage_flow.py. Only the entries given are changed.
    triage_thresholds: dict[str, dict[str, float]] = field(default_factory=dict)
    # voter -> question type -> whether that voter may answer that type. Only the entries given are changed.
    triage_enabled: dict[str, dict[str, bool]] = field(default_factory=lambda: {v: dict(t) for v, t in DEFAULT_TRIAGE_ENABLED.items()})
    # question type -> the voters asked, first to last (llm/triage_flow.py). A voter left out is never asked.
    triage_order: dict[str, tuple[str, ...]] = field(default_factory=lambda: dict(DEFAULT_TRIAGE_ORDER))
    # After the models answered a choice, options whose averaged probability is below
    # this share of the leading option's are dropped and the question is asked again (0 = never drop).
    triage_prune_ratio: float = 0.25
    # With two options left and Laya and the fallback still disagreeing, each option's confidence-weighted
    # probabilities are compared. The pick stands when the smaller of the two differences is below this
    # share of the larger one; otherwise the answer is unsure between both options.
    triage_pair_ratio: float = 0.5
    auto_tier: AutoTierSettings = AutoTierSettings()
    auto_route: AutoRouteSettings = AutoRouteSettings()

    def voters(self, kind: str) -> tuple[str, ...]:
        """The voters that may answer a question of this type, in the order they are asked."""
        return tuple(v for v in self.triage_order[kind] if self.triage_enabled[v][kind])

    def chain(self, feature: str) -> tuple[str, ...]:
        return self.chains.get(feature, DEFAULT_CHAIN)


@catalog
def settings() -> ClassifierSettings:
    """The `classifier` section of config_tuning.json over the defaults above (all off)."""
    return _load_settings()


@lru_cache(maxsize=1)
def _load_settings() -> ClassifierSettings:
    raw = read_section(TUNING_PATH, _SECTION, {})
    if not isinstance(raw, dict):
        raise ValueError(f"config_tuning.json {_SECTION} must be an object")
    unknown = set(raw) - _KNOWN - _RETIRED
    if unknown:
        raise ValueError(f"config_tuning.json {_SECTION} has unknown field(s): {', '.join(sorted(unknown))}")
    base = ClassifierSettings()
    timeout = raw.get("timeout_seconds", base.timeout_seconds)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
        raise ValueError(f"config_tuning.json {_SECTION}.timeout_seconds must be a number above 0 and at most 60")
    cap = raw.get("max_input_chars", base.max_input_chars)
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise ValueError(f"config_tuning.json {_SECTION}.max_input_chars must be a positive integer")
    if not isinstance(raw.get("triage_fallback", False), bool):
        raise ValueError(f"config_tuning.json {_SECTION}.triage_fallback must be true or false")
    ratio = raw.get("triage_prune_ratio", base.triage_prune_ratio)
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 <= ratio < 1:
        raise ValueError(f"config_tuning.json {_SECTION}.triage_prune_ratio must be a number from 0 up to (not including) 1")
    trace = raw.get("triage_trace", base.triage_trace)
    if not isinstance(trace, bool):
        raise ValueError(f"config_tuning.json {_SECTION}.triage_trace must be true or false")
    window = raw.get("triage_window", base.triage_window)
    if isinstance(window, bool) or not isinstance(window, int) or not 512 <= window <= 32_768:
        raise ValueError(f"config_tuning.json {_SECTION}.triage_window must be an integer from 512 to 32768")
    pair = raw.get("triage_pair_ratio", base.triage_pair_ratio)
    if isinstance(pair, bool) or not isinstance(pair, (int, float)) or not 0 < pair <= 1:
        raise ValueError(f"config_tuning.json {_SECTION}.triage_pair_ratio must be a number above 0 and at most 1")
    enabled = _triage_enabled(raw.get("triage_enabled", {}))
    return ClassifierSettings(
        triage_enabled=enabled, triage_order=_triage_order(raw.get("triage_order", {}), enabled),
        triage_trace=trace, triage_window=window, triage_thresholds=_triage_thresholds(raw.get("triage_thresholds", {})),
        triage_pair_ratio=float(pair),
        triage_prune_ratio=float(ratio),
        typesafe=_backend_settings("typesafe", raw.get("typesafe", {}), base.typesafe),
        vercel=_backend_settings("vercel", raw.get("vercel", {}), base.vercel),
        chains=_chains(raw.get("chains", {})),
        timeout_seconds=float(timeout), max_input_chars=cap, triage_fallback=raw.get("triage_fallback", False),
        auto_tier=_auto_tier_settings(raw.get("auto_tier", {})),
        auto_route=_auto_route_settings(raw.get("auto_route", {})),
    )


def _backend_settings(name: str, raw: Any, base: BackendSettings) -> BackendSettings:
    where = f"config_tuning.json {_SECTION}.{name}"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object")
    unknown = set(raw) - _BACKEND_KNOWN
    if unknown:
        raise ValueError(f"{where} has unknown field(s): {', '.join(sorted(unknown))}")
    values = {}
    for key in ("url", "model"):
        value = raw.get(key, getattr(base, key))
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{where}.{key} must be a non-empty string")
        values[key] = value.strip()
    return BackendSettings(**values)


def _triage_thresholds(raw: Any) -> dict[str, dict[str, float]]:
    where = f"config_tuning.json {_SECTION}.triage_thresholds"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object of option count ({', '.join(TRIAGE_COUNTS)}): voter: confidence")
    out: dict[str, dict[str, float]] = {}
    for count, row in raw.items():
        if count not in TRIAGE_COUNTS or not isinstance(row, dict):
            raise ValueError(f"{where} has an entry {count!r}; the counts are {', '.join(TRIAGE_COUNTS)}, each an object")
        for voter, value in row.items():
            if voter not in TRIAGE_VOTERS:
                raise ValueError(f"{where}.{count} names an unknown voter {voter!r} (use {', '.join(TRIAGE_VOTERS)})")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
                raise ValueError(f"{where}.{count}.{voter} must be a number above 0 and at most 1")
        out[count] = {voter: float(value) for voter, value in row.items()}
    return out


def _triage_enabled(raw: Any) -> dict[str, dict[str, bool]]:
    where = f"config_tuning.json {_SECTION}.triage_enabled"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object of voter: {{type: true or false}}")
    out = {voter: dict(kinds) for voter, kinds in DEFAULT_TRIAGE_ENABLED.items()}
    for voter, kinds in raw.items():
        if voter not in TRIAGE_VOTERS or not isinstance(kinds, dict):
            raise ValueError(f"{where} has an entry {voter!r}; the voters are {', '.join(TRIAGE_VOTERS)}, each an object")
        for kind, value in kinds.items():
            if kind not in TRIAGE_TYPES:
                raise ValueError(f"{where}.{voter} names an unknown question type {kind!r} (use {', '.join(TRIAGE_TYPES)})")
            if not isinstance(value, bool):
                raise ValueError(f"{where}.{voter}.{kind} must be true or false")
            out[voter][kind] = value
    return out


def _triage_order(raw: Any, enabled: dict[str, dict[str, bool]]) -> dict[str, tuple[str, ...]]:
    where = f"config_tuning.json {_SECTION}.triage_order"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object of question type: [voter, ...]")
    out = dict(DEFAULT_TRIAGE_ORDER)
    for kind, voters in raw.items():
        if kind not in TRIAGE_TYPES:
            raise ValueError(f"{where} names an unknown question type {kind!r} (use {', '.join(TRIAGE_TYPES)})")
        if not isinstance(voters, list) or not voters or any(v not in TRIAGE_VOTERS for v in voters) or len(set(voters)) != len(voters):
            raise ValueError(f"{where}.{kind} must be a list of distinct voters from: {', '.join(TRIAGE_VOTERS)}")
        out[kind] = tuple(voters)
    # The fallback is the last resort of a choice question: it is asked once the local models are done.
    if "jev" in out["choice"] and out["choice"][-1] != "jev":
        raise ValueError(f"{where}.choice must list jev last: it is asked after the Laya models")
    for kind, voters in out.items():
        if not any(enabled[v][kind] for v in voters):
            raise ValueError(f"{where}.{kind} lists no voter that triage_enabled allows to answer {kind} questions")
    return out


def _chains(raw: Any) -> dict[str, tuple[str, ...]]:
    where = f"config_tuning.json {_SECTION}.chains"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object of feature: [backend, ...]")
    chains: dict[str, tuple[str, ...]] = {}
    for feature, ids in raw.items():
        if feature not in FEATURES:
            raise ValueError(f"{where} names an unknown feature {feature!r} (use {', '.join(FEATURES)})")
        if not isinstance(ids, list) or not ids or any(i not in _BACKENDS for i in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"{where}.{feature} must be a list of distinct backends from: {', '.join(_BACKENDS)}")
        chains[feature] = tuple(ids)
    return chains


def _auto_route_settings(raw: Any) -> AutoRouteSettings:
    where = f"config_tuning.json {_SECTION}.auto_route"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object")
    unknown = set(raw) - _AUTO_ROUTE_KNOWN
    if unknown:
        raise ValueError(f"{where} has unknown field(s): {', '.join(sorted(unknown))}")
    if not isinstance(raw.get("enabled", False), bool):
        raise ValueError(f"{where}.enabled must be true or false")
    confidence = raw.get("min_confidence", AutoRouteSettings.min_confidence)
    if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100:
        raise ValueError(f"{where}.min_confidence must be an integer from 0 to 100")
    return AutoRouteSettings(enabled=raw.get("enabled", False), min_confidence=confidence)


def _auto_tier_settings(raw: Any) -> AutoTierSettings:
    from src.agents.agent_spec import TIERS  # imported here: agent_spec pulls in the llm package

    where = f"config_tuning.json {_SECTION}.auto_tier"
    if not isinstance(raw, dict):
        raise ValueError(f"{where} must be an object")
    unknown = set(raw) - _AUTO_TIER_KNOWN
    if unknown:
        raise ValueError(f"{where} has unknown field(s): {', '.join(sorted(unknown))}")
    if not isinstance(raw.get("enabled", False), bool):
        raise ValueError(f"{where}.enabled must be true or false")
    confidence = raw.get("min_confidence", AutoTierSettings.min_confidence)
    if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100:
        raise ValueError(f"{where}.min_confidence must be an integer from 0 to 100")
    mapping = dict(DEFAULT_SIZE_TIERS)
    given = raw.get("tiers", {})
    if not isinstance(given, dict):
        raise ValueError(f"{where}.tiers must be an object of size: tier")
    for size, tier in given.items():
        if size not in SIZE_CRITERIA or tier not in TIERS:
            raise ValueError(f"{where}.tiers maps a size ({', '.join(SIZE_CRITERIA)}) to a tier ({', '.join(TIERS)})")
        mapping[size] = tier
    return AutoTierSettings(enabled=raw.get("enabled", False), min_confidence=confidence, tiers=tuple(mapping.items()))


def reset_cache() -> None:
    """Forget the loaded settings (tests, and a config edit in a long-lived process)."""
    _load_settings.cache_clear()


def post_json(url: str, payload: dict[str, Any], key: str, timeout: float, what: str) -> dict[str, Any]:
    """POST `payload` as JSON with a bearer key; every failure is a ClassifierError naming `what`."""
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise ClassifierError(f"{what} answered HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ClassifierError(f"{what} could not be reached: {error}") from error
    except ValueError as error:
        raise ClassifierError(f"{what} sent something that is not JSON") from error


def _backend(backend_id: str) -> Any:
    return importlib.import_module(_BACKENDS[backend_id])


def _usable(feature: str, exclude: tuple[str, ...]) -> list[str]:
    return [i for i in settings().chain(feature) if i not in exclude and _backend(i).available()]


def available(feature: str, exclude: tuple[str, ...] = ()) -> bool:
    """True when some backend of the feature's chain can be asked; whether the feature is switched on is `settings()`."""
    return bool(_usable(feature, exclude))


@catalog
def ask_choice(
    subject: str, criteria: Mapping[str, str], question: str, feature: str, *,
    min_confidence: int | None = None, exclude: tuple[str, ...] = (), timeout: float | None = None,
) -> Choice:
    """Which of `criteria` (option -> one-line description) answers `question` about `subject`, and
    how sure, walking the feature's backend chain. `min_confidence` (0-100) hands a less sure answer
    on to the next backend; the last answer is returned either way. Raises ClassifierError when
    nothing could be asked or every backend failed."""
    if len(criteria) < 2:
        raise ClassifierError("a choice needs at least two options")
    if feature not in FEATURES:
        raise ValueError(f"unknown classifier feature {feature!r}")
    limit = timeout or settings().timeout_seconds
    chain = _usable(feature, exclude)
    if not chain:
        raise ClassifierError(f"no classifier backend is available for {feature} (chain: {', '.join(settings().chain(feature))})")
    answer: Choice | None = None
    failure: ClassifierError | None = None
    for backend_id in chain:
        try:
            answer = _backend(backend_id).ask_choice(subject, criteria, question, limit)
        except ClassifierError as error:
            _log.warning("classifier backend %s could not answer: %s", backend_id, error)
            failure = error
            continue
        if min_confidence is None or answer.confidence >= min_confidence:
            break
    if answer is None:
        raise failure or ClassifierError("no classifier backend answered")
    return answer


@catalog
def classify_size(message: str, timeout: float | None = None) -> Choice:
    """How hard `message` looks: one of SIZE_CRITERIA's names, with the backend's confidence."""
    return ask_choice(
        message, SIZE_CRITERIA, SIZE_QUESTION, "auto_tier",
        min_confidence=settings().auto_tier.min_confidence, timeout=timeout,
    )
