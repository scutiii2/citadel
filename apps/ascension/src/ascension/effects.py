"""Validation of an ability's `effects` list (catalog abilities and tree nodes)."""

from __future__ import annotations

import re
from typing import Any, Mapping

from src.ascension.models import EffectSpec

KINDS = ("heal", "regen", "bleed", "slow", "weaken", "exposed", "mark", "cleanse", "ward")
PERCENT_KINDS = ("heal", "regen", "bleed", "slow", "weaken", "exposed")
ROUND_KINDS = ("regen", "bleed", "slow", "weaken", "exposed", "mark", "ward")
FIELDS = {"kind", "percentage", "rounds", "name", "target"}
MAX_EFFECTS = 3


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def parse_effects(raw: Any, where: str) -> tuple[EffectSpec, ...]:
    """The effects of one ability. Raises ValueError with the place and the problem."""
    if not isinstance(raw, list):
        raise ValueError(f"{where}: effects must be a list")
    if len(raw) > MAX_EFFECTS:
        raise ValueError(f"{where}: at most {MAX_EFFECTS} effects")
    parsed = []
    for index, item in enumerate(raw):
        at = f"{where} effect {index}"
        if not isinstance(item, Mapping):
            raise ValueError(f"{at}: must be an object")
        extra = set(item) - FIELDS
        if extra:
            raise ValueError(f"{at}: unknown field {sorted(extra)[0]!r}")
        kind = item.get("kind")
        if kind not in KINDS:
            raise ValueError(f"{at}: unknown effect kind {kind!r}")
        percentage, rounds = item.get("percentage"), item.get("rounds")
        if kind in PERCENT_KINDS and not (_number(percentage) and percentage > 0):
            raise ValueError(f"{at}: {kind} needs a positive percentage")
        if kind in ROUND_KINDS and (isinstance(rounds, bool) or not isinstance(rounds, int) or rounds < 1):
            raise ValueError(f"{at}: {kind} needs rounds of at least 1")
        name, target = item.get("name"), item.get("target")
        if kind == "mark":
            if not isinstance(name, str) or not re.fullmatch(r"[a-z_]+", name):
                raise ValueError(f"{at}: a mark needs a lowercase name (letters and underscores)")
            target = target or "foe"
            if target not in ("foe", "self"):
                raise ValueError(f"{at}: a mark target must be foe or self")
        elif name is not None or target is not None:
            raise ValueError(f"{at}: only a mark has a name or a target")
        parsed.append(EffectSpec(
            kind, float(percentage) if kind in PERCENT_KINDS else None, rounds if kind in ROUND_KINDS else None, name, target))
    return tuple(parsed)
