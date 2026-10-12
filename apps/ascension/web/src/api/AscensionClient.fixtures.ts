import type { AscendedArtInfo, BattleView, Catalog, EncounterPreview, Fighter, OwnedAscended, Profile, AscendedInfo, ShopOffer, ShopWindow, TierInfo } from "./AscensionClient";

/** Test data shaped like Ascension's answers, for the Ascension tests. */

const nameOf = (id: string) => id.charAt(0).toUpperCase() + id.slice(1);

export function tier(id: string, emblemPrice: number, starsToAdvance: number | null): TierInfo {
  return { id, stat_multiplier: 1, stars_to_advance: starsToAdvance, essence_cost: 1, copy_reward: 1, emblem_strength: 1, emblem_price: emblemPrice };
}

const SHIPPED_FOCUS: Record<string, [number, number]> = {
  guardian: [21, 50], scout: [10, 50], striker: [10, 50], sentinel: [12, 14], channeler: [30, 43], forbidden: [18, 29],
};

/** The art block the game sends: the six shipped Ascended have all three sprites, the others none. */
export function artFor(id: string): AscendedArtInfo {
  const focus = SHIPPED_FOCUS[id];
  const url = (name: string) => (focus ? `/ascended/${id}/sprite_${name}.webp` : null);
  return { main_card: url("main_card"), preview_card: url("preview_card"), battle: url("battle"), focus: focus?.[0] ?? 50, focus_preview: focus?.[1] ?? 50 };
}

export function ascendedInfo(id: string, extra: Partial<AscendedInfo> = {}): AscendedInfo {
  return {
    id,
    name: nameOf(id),
    starter: false,
    forbidden: false,
    start_tier: "common",
    ascension_types: ["enchant"],
    base: { hp: 100, power: 10, speed: 10 },
    growth: { hp: 5, power: 1, speed: 1 },
    base_price: 50,
    passive: { kind: "steady", params: {} },
    abilities: [
      { id: `${id}_strike`, name: "Strike", unlock_level: 1, category: "ATTACK", percentage: 120, cooldown: 1, stat: null, duration: null },
      { id: `${id}_rally`, name: "Rally", unlock_level: 5, category: "SUPPORT", percentage: 50, cooldown: 3, stat: "power", duration: 2 },
    ],
    tree: [],
    art: artFor(id),
    ...extra,
  };
}

export const CATALOG: Catalog = {
  version: 1,
  tiers: [
    tier("common", 10, 1),
    tier("rare", 40, 2),
    tier("unique", 90, 3),
    tier("royal", 150, 5),
    tier("legendary", 250, null),
    tier("forbidden", 500, null),
  ],
  levels: { regular_cap: 30, forbidden_cap: 50 },
  ascendeds: [
    ascendedInfo("guardian", { starter: true }),
    ascendedInfo("striker", { starter: true }),
    ascendedInfo("bruiser"),
    ascendedInfo("forbidden", { forbidden: true, start_tier: "forbidden" }),
  ],
  personalities: [
    { id: "AGGRESSIVE", categories: ["ATTACK"] },
    { id: "CAUTIOUS", categories: ["DEFENSE"] },
  ],
};

export function ownedAscended(id: string, extra: Partial<OwnedAscended> = {}): OwnedAscended {
  return {
    ascended_id: id,
    name: nameOf(id),
    ascension_types: ["enchant"],
    level: 3,
    xp: 40,
    xp_needed: 300,
    level_cap: 30,
    copies: 1,
    tier_id: "common",
    stars: 0,
    stars_needed: 1,
    star_essence_cost: 1,
    next_tier_id: "rare",
    can_star_up: false,
    can_tier_up: false,
    faint_until: null,
    fainted: false,
    ...extra,
  };
}

export const PROFILE: Profile = {
  owner: "1",
  insignia: 100,
  emblems: { common: 2 },
  essences: {},
  ascendeds: [ownedAscended("guardian")],
  pending_encounter: null,
  active_battle: null,
  next_roll_at: null,
};

export const ENCOUNTER: EncounterPreview = {
  id: "e1",
  ascended_id: "bruiser",
  name: "Bruiser",
  tier_id: "rare",
  level: 4,
  status: "pending",
  created_at: 1_700_000_000,
};

export function fighter(ascendedId: string, extra: Partial<Fighter> = {}): Fighter {
  return {
    ascended_id: ascendedId,
    name: nameOf(ascendedId),
    tier_id: "common",
    level: 3,
    hp: 80,
    max_hp: 100,
    power: 12,
    speed: 9,
    buffs: [],
    defense: null,
    abilities: [{ id: `${ascendedId}_strike`, name: "Strike", category: "ATTACK", percentage: 120, cooldown: 1, ready: true }],
    ...extra,
  };
}

export function battleView(extra: Partial<BattleView> = {}): BattleView {
  return {
    id: "b1",
    status: "active",
    phase: "choosing",
    mode: "autonomous",
    round: 1,
    revision: 1,
    emblem_limit: "common",
    player: fighter("guardian"),
    wild: fighter("bruiser"),
    actions: [
      { kind: "attack", category: "ATTACK", ability_id: null, name: null, percentage: 100 },
      { kind: "ability", category: "ATTACK", ability_id: "guardian_strike", name: "Strike", percentage: 120 },
      { kind: "flee", category: "FEAR", ability_id: null, name: null, percentage: 100 },
      { kind: "catch", category: "INTERCEPT", ability_id: null, name: null, percentage: 100 },
    ],
    emblems: { common: 2 },
    prompt: null,
    history: [],
    result: null,
    ...extra,
  };
}

export function shopOffer(extra: Partial<ShopOffer> = {}): ShopOffer {
  return {
    slot: 0, ascended_id: "guardian", tier_id: "common", copies_granted: 1, stock: 3, left: 3,
    price: 40, owned: false, owned_copies: 0, ...extra,
  };
}

export function shopWindow(extra: Partial<ShopWindow> = {}): ShopWindow {
  return {
    rotation: 46, refreshes_at: 1_015_200, seconds_left: 3600,
    offers: [shopOffer(), shopOffer({ slot: 1, ascended_id: "scout", tier_id: "rare", stock: 1, left: 1, price: 90 })],
    ...extra,
  };
}
