"""The versioned game catalog: Ascended, abilities, tiers, personalities, the
economy and the action-policy numbers. Loaded and validated once at startup.

Balance numbers are initial values; changing the file affects future battles
only (a battle freezes its fighters when it starts).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.ascension.ascension_types import AscensionType
from src.ascension.effects import parse_effects
from src.ascension.match_state import MoodConstants
from src.ascension.personality_rules import Rule, parse_rules
from src.ascension.models import ABILITY_CATEGORIES, CATEGORIES, AbilitySpec, PassiveSpec, Loadout
from src.ascension.passives import PassiveFactory
from src.ascension.tree import AbilityTree, NodeCost, TreeError, TreeNode, passive_root_id

ABILITY_UNLOCK_LEVELS = (1, 10, 20)
# The catalog always sits in the same place in the project tree, so it has no config entry.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = PROJECT_ROOT / "configs" / "ascension_catalog.json"
ASCENDEDS_PATH = PROJECT_ROOT / "ascended"
ASCENDED_FILE = "catalog.json"
TREE_FILE = "tree.json"
# The sprite files an Ascended folder may hold, in the order main card, small card, battle.
SPRITE_NAMES = ("sprite_main_card.webp", "sprite_preview_card.webp", "sprite_battle.webp")
STATS = ("hp", "power", "speed")


class CatalogError(ValueError):
    """The catalog file is missing a field or holds an inconsistent value."""


@dataclass(frozen=True)
class TierSpec:
    id: str
    stat_multiplier: float
    capture_multiplier: float
    hp_floor: float
    emblem_strength: int
    emblem_price: int
    encounter_probability: float
    stars_to_advance: int | None  # stars that unlock the next tier; None = top of the ladder (Legendary, Forbidden)
    essence_cost: int  # essence of this tier spent per star, and earned from beating an enemy of this tier
    copy_reward: int


@dataclass(frozen=True)
class ArtSpec:
    """Which sprites an Ascended's folder holds, and where to centre the crop (percent, like CSS object-position)."""

    main_card: bool = False
    preview_card: bool = False
    battle: bool = False
    focus: float = 50
    focus_preview: float = 50


@dataclass(frozen=True)
class AscendedSpec:
    id: str
    name: str
    starter: bool
    forbidden: bool
    base_price: int
    start_tier: str | None  # None = the first regular tier (Forbidden is always the Forbidden tier)
    base: Mapping[str, float]
    growth: Mapping[str, float]
    passive: PassiveSpec
    abilities: tuple[AbilitySpec, ...]
    ascension_types: tuple[AscensionType, ...] = ()
    art: ArtSpec = ArtSpec()
    tree: AbilityTree | None = None  # Set by _ascended_spec, with roots when no tree.json exists.


@dataclass(frozen=True)
class PersonalitySpec:
    id: str
    categories: tuple[str, ...]
    rules: tuple[Rule, ...] = ()


@dataclass(frozen=True)
class PolicySpec:
    gain: float
    off_mood_factor: float
    repeat_factor: float
    floor: float
    default_aggression: float
    default_flee_share: float
    coefficients: Mapping[str, Mapping[str, float]]
    potency_weight: float = 0.3  # stage 2: weight of how strong an ability is inside its category
    pick_weight: float = 1.5  # stage 2: weight of pick_by_percentage rules
    temperature: float = 0.7  # stage 2: softmax temperature
    counter_boost: float = 3.0  # stage 1: boost of the counter or copied category at full strength
    mood: MoodConstants = MoodConstants()


@dataclass(frozen=True)
class Economy:
    xp_reward_factor: float
    insignia_reward_factor: float
    sale_level_bonus: float
    purchase_factor: float
    forbidden_copy_cap: int
    base_capture_resistance: float
    starter_emblems: Mapping[str, int]
    starter_personality_tier: int
    encounter_level_window: int
    personality_tier_probabilities: tuple[float, ...]


@dataclass(frozen=True)
class ShopSpec:
    """Per regular tier: how many times one offer can be bought, and how likely the tier is to be offered."""

    stock: Mapping[str, int]
    tier_weights: Mapping[str, float]


@dataclass(frozen=True)
class Levels:
    regular_cap: int
    forbidden_cap: int
    xp_per_level: int


def _require(raw: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in raw:
        raise CatalogError(f"{where}: missing {key!r}")
    return raw[key]


def _ability(raw: Mapping[str, Any], ascended_id: str) -> AbilitySpec:
    where = f"ascended {ascended_id!r} ability {raw.get('id')!r}"
    try:
        effects = parse_effects(raw.get("effects", []), where)
    except ValueError as error:
        raise CatalogError(str(error)) from error
    ability = AbilitySpec(
        id=_require(raw, "id", where), name=_require(raw, "name", where),
        unlock_level=_require(raw, "unlock_level", where), category=_require(raw, "category", where),
        percentage=float(_require(raw, "percentage", where)), cooldown=_require(raw, "cooldown", where),
        stat=raw.get("stat"), duration=raw.get("duration"), effects=effects,
    )
    if ability.category not in ABILITY_CATEGORIES:
        raise CatalogError(f"{where}: category must be one of {ABILITY_CATEGORIES}")
    if ability.cooldown < 1 or ability.percentage <= 0:
        raise CatalogError(f"{where}: cooldown must be at least 1 and percentage positive")
    if ability.category == "SUPPORT" and (ability.stat not in ("power", "speed") or not ability.duration or ability.duration < 1):
        raise CatalogError(f"{where}: SUPPORT needs a stat (power or speed) and a duration of at least 1")
    return ability


def _art(raw: Mapping[str, Any], where: str) -> ArtSpec:
    art = raw.get("art", {})
    if not isinstance(art, Mapping) or set(art) - {"focus", "focus_preview"}:
        raise CatalogError(f"{where}: art may only set focus and focus_preview")
    focus = {}
    for key in ("focus", "focus_preview"):
        value = art.get(key, 50)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise CatalogError(f"{where}: art {key} must be a number from 0 to 100")
        focus[key] = value
    found = raw.get("sprites", [])
    return ArtSpec(*(name in found for name in SPRITE_NAMES), **focus)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _tree(raw: Any, spec_id: str, abilities: tuple[AbilitySpec, ...], passive: PassiveSpec) -> AbilityTree:
    """The Ascended's tree: its roots (the catalog kit) plus any nodes in tree.json."""
    where = f"ascended {spec_id!r} tree"
    root_abilities = {a.id: a for a in abilities}
    passive_id = passive_root_id(spec_id)
    if raw is None:
        raw = {"nodes": [{"id": i, "root": True, "x": 40, "y": 60 + 110 * n}
                         for n, i in enumerate([*root_abilities, passive_id])]}
    if not isinstance(raw, Mapping) or set(raw) - {"nodes"} or not isinstance(raw.get("nodes", []), list):
        raise CatalogError(f"{where}: only nodes is allowed, as a list")
    nodes: list[TreeNode] = []
    listed_roots: list[str] = []
    for item in raw.get("nodes", []):
        node_id = item.get("id") if isinstance(item, Mapping) else None
        if not isinstance(node_id, str):
            raise CatalogError(f"{where}: every node needs an id")
        at = f"{where} node {node_id!r}"
        if not _number(item.get("x")) or not _number(item.get("y")):
            raise CatalogError(f"{at}: x and y must be numbers")
        x, y = item["x"], item["y"]
        if item.get("root"):
            if item.get("requires"):
                raise CatalogError(f"{at}: a root cannot have requirements")
            listed_roots.append(node_id)
            if node_id == passive_id:
                nodes.append(TreeNode(node_id, "passive", passive.kind.replace("_", " ").title(), x, y, root=True, passive=passive))
            elif node_id in root_abilities:
                a = root_abilities[node_id]
                nodes.append(TreeNode(node_id, "ability", a.name, x, y, unlock_level=a.unlock_level, root=True, ability=a))
            else:
                raise CatalogError(f"{at}: a root must be one of the catalog abilities or {passive_id!r}")
            continue
        requires = item.get("requires", [])
        if not isinstance(requires, list) or any(not isinstance(r, str) for r in requires):
            raise CatalogError(f"{at}: requires must be a list of node ids")
        cost_raw = item.get("cost")
        if not isinstance(cost_raw, Mapping):
            raise CatalogError(f"{at}: needs a cost with a tier and an amount")
        amount = cost_raw.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1 or not isinstance(cost_raw.get("tier"), str):
            raise CatalogError(f"{at}: cost needs a tier and a whole amount of at least 1")
        cost = NodeCost(cost_raw["tier"], amount)
        kind = item.get("kind")
        if kind == "ability":
            a = _ability(item, spec_id)
            nodes.append(TreeNode(node_id, "ability", a.name, x, y, tuple(requires), a.unlock_level, cost, ability=a))
        elif kind == "passive":
            body = item.get("passive")
            level = item.get("unlock_level")
            if not isinstance(body, Mapping) or "kind" not in body or isinstance(level, bool) or not isinstance(level, int) or level < 1:
                raise CatalogError(f"{at}: a passive node needs a passive (kind, params) and a whole unlock_level of at least 1")
            spec = PassiveSpec(body["kind"], dict(body.get("params", {})))
            try:
                PassiveFactory().create(spec)
            except (ValueError, TypeError) as error:
                raise CatalogError(f"{at}: unknown passive or bad params ({error})") from error
            nodes.append(TreeNode(node_id, "passive", str(item.get("name", node_id)), x, y, tuple(requires), level, cost, passive=spec))
        else:
            raise CatalogError(f"{at}: kind must be ability or passive")
    if raw.get("nodes") and sorted(listed_roots) != sorted([*root_abilities, passive_id]):
        raise CatalogError(f"{where}: must list every root: {', '.join([*root_abilities, passive_id])}")
    try:
        return AbilityTree(nodes)
    except TreeError as error:
        raise CatalogError(f"{where}: {error}") from error


def _ascended_spec(raw: Mapping[str, Any]) -> AscendedSpec:
    sid = _require(raw, "id", "ascended")
    where = f"ascended {sid!r}"
    base, growth = _require(raw, "base", where), _require(raw, "growth", where)
    if set(base) != set(STATS) or set(growth) != set(STATS):
        raise CatalogError(f"{where}: base and growth need exactly hp, power and speed")
    abilities = tuple(_ability(a, sid) for a in _require(raw, "abilities", where))
    if tuple(a.unlock_level for a in abilities) != ABILITY_UNLOCK_LEVELS:
        raise CatalogError(f"{where}: abilities must unlock at levels {ABILITY_UNLOCK_LEVELS}")
    passive = _require(raw, "passive", where)
    try:
        ascension_types = AscensionType.parse_all(raw.get("ascension_types", []), where)
    except ValueError as error:
        raise CatalogError(str(error)) from error
    passive_spec = PassiveSpec(_require(passive, "kind", f"{where} passive"), dict(passive.get("params", {})))
    return AscendedSpec(
        id=sid, name=_require(raw, "name", where), starter=bool(raw.get("starter")), forbidden=bool(raw.get("forbidden")),
        base_price=_require(raw, "base_price", where), start_tier=raw.get("start_tier"), base=dict(base), growth=dict(growth),
        passive=passive_spec, abilities=abilities,
        ascension_types=ascension_types, art=_art(raw, where),
        tree=_tree(raw.get("tree"), sid, abilities, passive_spec),
    )


class Catalog:
    def __init__(self, raw: Mapping[str, Any]) -> None:
        self.ascendeds_path: Path | None = None
        try:
            self._build(raw)
        except CatalogError:
            raise
        except (TypeError, KeyError, AttributeError, ValueError, IndexError) as error:
            raise CatalogError(f"malformed catalog: {type(error).__name__}: {error}") from error

    @staticmethod
    def _rules(raw_personality: Mapping[str, Any]) -> tuple[Rule, ...]:
        try:
            return parse_rules(raw_personality.get("rules", []), f"personality {raw_personality['id']!r}")
        except ValueError as error:
            raise CatalogError(str(error)) from error

    def _build(self, raw: Mapping[str, Any]) -> None:
        if not isinstance(raw, Mapping):
            raise CatalogError("catalog must be an object")
        self.version: int = _require(raw, "version", "catalog")
        self.tiers: tuple[TierSpec, ...] = tuple(TierSpec(**t) for t in _require(raw, "tiers", "catalog"))
        self.levels = Levels(**_require(raw, "levels", "catalog"))
        shop = _require(raw, "shop", "catalog")
        self.shop = ShopSpec(dict(_require(shop, "stock", "shop")), dict(_require(shop, "tier_weights", "shop")))
        economy = dict(_require(raw, "economy", "catalog"))
        economy["personality_tier_probabilities"] = tuple(economy["personality_tier_probabilities"])
        self.economy = Economy(**economy)
        personalities = [PersonalitySpec(p["id"], tuple(p["categories"]), self._rules(p)) for p in _require(raw, "personalities", "catalog")]
        self.personalities: dict[str, PersonalitySpec] = {p.id: p for p in personalities}
        if len(self.personalities) != len(personalities):
            raise CatalogError("personality ids must be unique")
        policy = dict(_require(raw, "policy", "catalog"))
        policy["mood"] = MoodConstants(**policy.get("mood", {}))
        self.policy = PolicySpec(**policy)
        ascendeds = _require(raw, "ascendeds", "catalog")
        ascended_ids = [_require(s, "id", "ascended") for s in ascendeds]
        if len(set(ascended_ids)) != len(ascended_ids):
            raise CatalogError("ascended ids must be unique")
        catalog_ability_ids = [a["id"] for s in ascendeds for a in s["abilities"]]
        if len(set(catalog_ability_ids)) != len(catalog_ability_ids):
            raise CatalogError("ability ids must be unique across all Ascended")
        specs = [_ascended_spec(s) for s in ascendeds]
        self._ascendeds = {s.id: s for s in specs}
        if len(self._ascendeds) != len(specs):
            raise CatalogError("ascended ids must be unique")
        # Action keys and cooldowns key on the ability id, so it is unique across Ascended, and tree nodes share the id space.
        node_ids = [n.id for s in specs for n in s.tree.nodes]
        ability_ids = [n.id for s in specs for n in s.tree.nodes if n.kind == "ability"]
        if len(set(ability_ids)) != len(ability_ids):
            raise CatalogError("ability ids must be unique across all Ascended")
        if len(set(node_ids)) != len(node_ids):
            raise CatalogError("tree node ids must be unique across all Ascended")
        self._tiers = {t.id: t for t in self.tiers}
        self._validate()

    # -- validation ----------------------------------------------------------------

    def _validate(self) -> None:
        if len(self._tiers) != len(self.tiers):
            raise CatalogError("tier ids must be unique")
        if len(self.tiers) < 2:
            raise CatalogError("need at least one regular tier plus the Forbidden tier")
        for tier in self.tiers:
            if tier.stat_multiplier <= 0 or tier.capture_multiplier <= 0 or tier.encounter_probability < 0:
                raise CatalogError(f"tier {tier.id!r}: multipliers must be positive and probability non-negative")
        regular_tier_ids = {t.id for t in self.regular_tiers}
        for spec in self._ascendeds.values():
            if spec.base_price <= 0:
                raise CatalogError(f"ascended {spec.id!r}: base_price must be positive")
            if spec.start_tier is not None and (spec.forbidden or spec.start_tier not in regular_tier_ids):
                raise CatalogError(f"ascended {spec.id!r}: start_tier must be a regular tier (Forbidden has none)")
            for node in spec.tree.nodes:
                if node.cost is not None and node.cost.tier not in regular_tier_ids:
                    raise CatalogError(f"ascended {spec.id!r} tree node {node.id!r}: cost tier must be a regular tier")
        if not math.isclose(sum(t.encounter_probability for t in self.tiers), 1.0, abs_tol=1e-9):
            raise CatalogError("tier encounter probabilities must sum to 1")
        if not math.isclose(sum(self.economy.personality_tier_probabilities), 1.0, abs_tol=1e-9):
            raise CatalogError("personality tier probabilities must sum to 1")
        if self.tiers[-1].stars_to_advance is not None:
            raise CatalogError("the last tier (Forbidden) is outside the star ladder: stars_to_advance must be null")
        ladder = [t.stars_to_advance for t in self.regular_tiers]
        if ladder[-1] is not None or any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in ladder[:-1]):
            raise CatalogError("each regular tier but the last needs stars_to_advance of at least 1; the last needs null")
        if any(isinstance(t.essence_cost, bool) or not isinstance(t.essence_cost, int) or t.essence_cost < 1 for t in self.tiers):
            raise CatalogError("every tier needs an essence_cost of at least 1")
        regular_ids = {t.id for t in self.regular_tiers}
        if set(self.shop.stock) != regular_ids or set(self.shop.tier_weights) != regular_ids:
            raise CatalogError("shop stock and tier_weights must list exactly the regular tiers")
        if any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in self.shop.stock.values()):
            raise CatalogError("shop stock must be a whole number of at least 1 per tier")
        if any(isinstance(w, bool) or not isinstance(w, (int, float)) or w <= 0 for w in self.shop.tier_weights.values()):
            raise CatalogError("shop tier_weights must be positive numbers")
        if len([s for s in self._ascendeds.values() if s.starter]) != 3:
            raise CatalogError("exactly three Ascended must be starters")
        if len([s for s in self._ascendeds.values() if s.forbidden]) != 1:
            raise CatalogError("exactly one Ascended must be Forbidden")
        if any(s.starter and s.forbidden for s in self._ascendeds.values()):
            raise CatalogError("a starter cannot be Forbidden")
        for personality in self.personalities.values():
            if any(c not in CATEGORIES for c in personality.categories):
                raise CatalogError(f"personality {personality.id!r} has invalid categories")
        p, m = self.policy, self.policy.mood
        if p.temperature <= 0 or p.potency_weight < 0 or p.pick_weight < 0 or p.counter_boost < 1 or not 0 < p.repeat_factor <= 1:
            raise CatalogError("policy needs temperature > 0, potency_weight and pick_weight >= 0, counter_boost >= 1 and 0 < repeat_factor <= 1")
        if not (0 <= m.rage_decay <= 1 and m.rage_gain >= 0 and m.confidence_step >= 0 and 0 <= m.nerves_follow <= 1
                and 0 <= m.enemy_low <= 1 and m.streak_base >= 1 and m.streak_span >= 1):
            raise CatalogError("policy mood numbers are out of range")
        for category in CATEGORIES:
            if category not in self.policy.coefficients:
                raise CatalogError(f"policy coefficients missing for {category}")
        for tier_id in self.economy.starter_emblems:
            self.tier(tier_id)

    # -- lookups -------------------------------------------------------------------

    @classmethod
    def load(cls, catalog_path: Path = CATALOG_PATH, ascendeds_path: Path = ASCENDEDS_PATH) -> "Catalog":
        """Global rules from one file, the Ascended from one folder each (sorted by
        folder name, so the Ascended order and every draw over it stay deterministic)."""
        try:
            raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise CatalogError(f"cannot load catalog {catalog_path}: {error}") from error
        if not isinstance(raw, dict):
            raise CatalogError(f"cannot load catalog {catalog_path}: must be an object")
        raw["ascendeds"] = cls._load_ascendeds(ascendeds_path)
        catalog = cls(raw)
        catalog.ascendeds_path = ascendeds_path
        return catalog

    @staticmethod
    def _load_ascendeds(ascendeds_path: Path) -> list[Any]:
        if not ascendeds_path.is_dir():
            raise CatalogError(f"ascended directory {ascendeds_path} does not exist")
        folders = sorted((d for d in ascendeds_path.iterdir() if (d / ASCENDED_FILE).is_file()), key=lambda d: d.name)
        if not folders:
            raise CatalogError(f"ascended directory {ascendeds_path} holds no <ascended>/{ASCENDED_FILE} files")
        ascendeds: list[Any] = []
        for folder in folders:
            label = f"{folder.name}/{ASCENDED_FILE}"
            try:
                ascended = json.loads((folder / ASCENDED_FILE).read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise CatalogError(f"cannot load ascended file {label}: {error}") from error
            if not isinstance(ascended, dict) or ascended.get("id") != folder.name:
                found = ascended.get("id") if isinstance(ascended, dict) else ascended
                raise CatalogError(f"ascended file {label}: id {found!r} must equal the folder name {folder.name!r}")
            ascended["sprites"] = [name for name in SPRITE_NAMES if (folder / name).is_file()]
            tree_file = folder / TREE_FILE
            if tree_file.is_file():
                try:
                    ascended["tree"] = json.loads(tree_file.read_text(encoding="utf-8"))
                except (OSError, ValueError) as error:
                    raise CatalogError(f"cannot load tree file {folder.name}/{TREE_FILE}: {error}") from error
            ascendeds.append(ascended)
        return ascendeds

    def default_loadout(self, ascended_id: str) -> Loadout:
        """The starting kit: the catalog abilities in order and the catalog passive."""
        spec = self.ascended(ascended_id)
        return Loadout(spec.abilities, spec.passive)

    def sprite_path(self, ascended_id: str, file: str) -> Path | None:
        """The sprite file for a catalog Ascended and one of the three exact names, else None.
        The path is built from the catalog id and the fixed name, never from request text."""
        if self.ascendeds_path is None or file not in SPRITE_NAMES or ascended_id not in self._ascendeds:
            return None
        path = self.ascendeds_path / ascended_id / file
        return path if path.is_file() else None

    @property
    def regular_tiers(self) -> tuple[TierSpec, ...]:
        return self.tiers[:-1]

    @property
    def forbidden_tier(self) -> TierSpec:
        return self.tiers[-1]

    def tier(self, tier_id: str) -> TierSpec:
        try:
            return self._tiers[tier_id]
        except KeyError:
            raise CatalogError(f"unknown tier {tier_id!r}") from None

    def ascended(self, ascended_id: str) -> AscendedSpec:
        try:
            return self._ascendeds[ascended_id]
        except KeyError:
            raise CatalogError(f"unknown ascended {ascended_id!r}") from None

    def has_ascended(self, ascended_id: str) -> bool:
        return ascended_id in self._ascendeds

    def all_ascendeds(self) -> tuple[AscendedSpec, ...]:
        return tuple(self._ascendeds.values())

    def regular_ascendeds(self) -> tuple[AscendedSpec, ...]:
        return tuple(s for s in self._ascendeds.values() if not s.forbidden)

    def starter_ascendeds(self) -> tuple[AscendedSpec, ...]:
        return tuple(s for s in self._ascendeds.values() if s.starter)

    def forbidden_ascended(self) -> AscendedSpec:
        return next(s for s in self._ascendeds.values() if s.forbidden)

    def level_cap(self, ascended_id: str) -> int:
        return self.levels.forbidden_cap if self.ascended(ascended_id).forbidden else self.levels.regular_cap

    def stat_value(self, ascended_id: str, level: int, tier_id: str, stat: str) -> int:
        """Full-precision stat, then floored to a positive whole number."""
        spec = self.ascended(ascended_id)
        raw = (spec.base[stat] + spec.growth[stat] * (level - 1)) * self.tier(tier_id).stat_multiplier
        return max(1, math.floor(raw + 1e-9))

    def start_tier(self, ascended_id: str) -> str:
        """The tier an Ascended is first owned at."""
        spec = self.ascended(ascended_id)
        if spec.forbidden:
            return self.forbidden_tier.id
        return spec.start_tier or self.regular_tiers[0].id

    def tier_of(self, ascended_id: str, tier_id: str | None) -> str:
        """The tier an owned Ascended is at now: its saved tier, else its start tier. Forbidden never moves."""
        if self.ascended(ascended_id).forbidden or tier_id is None:
            return self.start_tier(ascended_id)
        return self.tier(tier_id).id

    def next_tier(self, tier_id: str) -> str | None:
        """The regular tier above `tier_id`, or None at the top of the ladder."""
        ids = [t.id for t in self.regular_tiers]
        position = ids.index(tier_id) if tier_id in ids else len(ids) - 1
        return ids[position + 1] if position + 1 < len(ids) else None

    def sale_value(self, ascended_id: str, tier_id: str, level: int) -> int:
        """Insignia for selling one copy of an Ascended at this tier and level."""
        spec = self.ascended(ascended_id)
        factor = 1 + self.economy.sale_level_bonus * (level - 1)
        return math.floor(spec.base_price * self.tier(tier_id).stat_multiplier * factor + 1e-9)
