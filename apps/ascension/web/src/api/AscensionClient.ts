import { useSessionStore } from "../stores/session";
import { HttpClient } from "./http";

/** The Ascension game (apps/ascension) through ember_api's /api/ascension
 * pass-through. Field names are Ascension's own. Every change carries an
 * Idempotency-Key: a fresh one per user action, unless the caller passes the
 * key of the action it is retrying. Times (`next_roll_at`, `faint_until`,
 * `deadline`, `created_at`) are server epoch seconds. */

export type BattleMode = "manual" | "autonomous";
export type ActionKind = "attack" | "ability" | "flee" | "catch";
export type ResultKind = "won" | "knocked_out" | "captured" | "escaped" | "wild_escaped" | "forfeited";
export type Side = "player" | "wild";

export interface TierInfo {
  id: string;
  stat_multiplier: number;
  /** Copies a regular Ascended needs for this tier; null for the Forbidden tier. */
  /** Stars that unlock the next tier; null at the top of the ladder. */
  stars_to_advance: number | null;
  /** Essence of this tier spent per star, and earned from beating an enemy of this tier. */
  essence_cost: number;
  copy_reward: number;
  emblem_strength: number;
  emblem_price: number;
}

export interface EffectInfo { kind: string; percentage?: number; rounds?: number; name?: string; target?: string }
export interface Status { id: string; amount: number; rounds_left: number }

export interface AbilityInfo {
  effects?: EffectInfo[];
  id: string;
  name: string;
  unlock_level: number;
  category: string;
  percentage: number;
  cooldown: number;
  stat: string | null;
  duration: number | null;
}

export type AnimationState = "idle" | "attack" | "defend" | "support" | "flee" | "catch";

/** The animation sheet of an Ascended: a grid of frames, one row per state, all facing right. */
export interface AnimationInfo {
  url: string;
  columns: number;
  rows: number;
  states: Partial<Record<AnimationState, { row: number; frames: number; frame_ms: number; loop: boolean }>>;
}

export interface AscendedArtInfo {
  main_card: string | null;
  preview_card: string | null;
  battle: string | null;
  /** Vertical crop centre, 0 to 100 (CSS object-position), for the main card and the preview card. */
  focus: number;
  focus_preview: number;
  /** Null when the Ascended has no sheet: the battle sprite then stays still. */
  animation: AnimationInfo | null;
}

export interface TreeCost { tier: string; amount: number }
export interface TreeNodeView {
  effects?: EffectInfo[];
  id: string; kind: "ability" | "passive"; name: string; x: number; y: number; requires: string[];
  unlock_level: number; root: boolean; cost: TreeCost | null;
  category?: string; percentage?: number; cooldown?: number; stat?: string | null; duration?: number | null;
  passive?: { kind: string; params: Record<string, unknown> };
}
export interface TreeNodeState extends TreeNodeView { state: "learned" | "learnable" | "locked"; reason: string | null }
export type LoadoutSlot = "a1" | "a2" | "a3" | "p1";
export interface TreeView {
  ascended_id: string; level: number; essences: Record<string, number>;
  nodes: TreeNodeState[]; loadout: Record<LoadoutSlot, string | null>;
}
export interface LearnResult { kind: "learn"; ascended_id: string; node_id: string; essence_tier: string; essence_spent: number }
export interface LoadoutResult { ascended_id: string; abilities: string[]; passive: string | null }

export interface AscendedInfo {
  id: string;
  name: string;
  starter: boolean;
  forbidden: boolean;
  /** The tier it is first owned at. */
  start_tier: string;
  /** Ascension Type ids; zero or more. */
  ascension_types: string[];
  base: Record<string, number>;
  growth: Record<string, number>;
  base_price: number;
  passive: { kind: string; params: Record<string, unknown> };
  abilities: AbilityInfo[];
  tree: TreeNodeView[];
  art: AscendedArtInfo;
}

export interface PersonalityRule {
  when: Record<string, number | string | boolean>;
  multiply?: Record<string, number>;
  chaos?: number;
  counter?: boolean;
  copy_enemy?: boolean;
  break_streak?: boolean;
  stay?: number;
  repeat?: number;
  pick_by_percentage?: "high" | "low";
}
export interface PersonalityInfo { id: string; categories: string[]; rules?: PersonalityRule[] }

export interface Catalog {
  version: number;
  /** Weakest first. */
  tiers: TierInfo[];
  levels: { regular_cap: number; forbidden_cap: number };
  ascendeds: AscendedInfo[];
  personalities: PersonalityInfo[];
  personality_off_mood_factor?: number;
}

export interface OwnedAscended {
  ascended_id: string;
  name: string;
  ascension_types: string[];
  level: number;
  xp: number;
  /** null at the level cap. */
  xp_needed: number | null;
  level_cap: number;
  /** Spare duplicates: one is spent per star, or sold. */
  copies: number;
  tier_id: string;
  stars: number;
  /** Stars that unlock the next tier; null at the top of the ladder. */
  stars_needed: number | null;
  /** Essence of its own tier that one star costs. */
  star_essence_cost: number;
  next_tier_id: string | null;
  can_star_up: boolean;
  can_tier_up: boolean;
  faint_until: number | null;
  fainted: boolean;
}

export interface Profile {
  owner: string;
  insignia: number;
  emblems: Record<string, number>;
  /** Upgrade material, by tier. */
  essences: Record<string, number>;
  ascendeds: OwnedAscended[];
  pending_encounter: string | null;
  active_battle: string | null;
  next_roll_at: number | null;
}

export interface PersonalityItem {
  id: string;
  type: string;
  tier: number;
}

export interface PersonalityPage {
  items: PersonalityItem[];
  next_cursor: number | null;
}

export interface Preset {
  ascended_id: string;
  slot: number;
  instance_ids: string[];
}

export interface EncounterPreview {
  id: string;
  ascended_id: string;
  name: string;
  tier_id: string;
  level: number;
  status: string;
  created_at: number;
}

export interface Buff {
  source: string;
  stat: string;
  amount: number;
  /** null: lasts the whole battle. */
  rounds_left: number | null;
}

export interface DefenseEffect {
  rating: number;
  attacks_left: number;
  rounds_left: number;
}

export interface FighterAbility {
  effects?: EffectInfo[];
  id: string;
  name: string;
  category: string;
  percentage: number;
  cooldown: number;
  ready: boolean;
}

export interface Fighter {
  statuses?: Status[];
  ascended_id: string;
  name: string;
  tier_id: string;
  level: number;
  hp: number;
  max_hp: number;
  power: number;
  speed: number;
  buffs: Buff[];
  defense: DefenseEffect | null;
  abilities: FighterAbility[];
}

export interface LegalAction {
  kind: ActionKind;
  category: string;
  ability_id: string | null;
  name: string | null;
  percentage: number;
  effects?: EffectInfo[];
}

export interface EmblemPromptState {
  /** Server time; the page never uses it (see seconds_left). */
  deadline: number;
  seconds_left: number;
  permitted_tiers: string[];
  owned: Record<string, number>;
}

export interface BattleEvent {
  type: string;
  side?: Side;
  [field: string]: unknown;
}

export interface HistoryRound {
  round: number;
  /** side -> [action key ("attack", "ability:<id>", "flee", "catch"), category] */
  actions: Record<Side, [string, string]>;
  events: BattleEvent[];
}

export interface RevealedPersonality {
  id: string;
  type: string;
  tier: number;
}

export interface BattleResult {
  kind: ResultKind;
  xp?: number;
  insignia?: number;
  essence?: number;
  essence_tier_id?: string;
  level_before?: number;
  level_after?: number;
  ascended_id?: string;
  copies_granted?: number;
  copies?: number;
  tier_id?: string;
  awarded_personality?: RevealedPersonality;
  revealed_personalities?: RevealedPersonality[];
  faint_until?: number;
}

export interface BattleView {
  id: string;
  status: "active" | "terminal";
  phase: "choosing" | "awaiting_emblem" | "terminal";
  mode: BattleMode;
  round: number;
  revision: number;
  emblem_limit: string | null;
  player: Fighter;
  wild: Fighter;
  actions: LegalAction[];
  emblems: Record<string, number>;
  prompt: EmblemPromptState | null;
  history: HistoryRound[];
  result: BattleResult | null;
}

/** The round and revision a round change was based on (a stale pair is a 409). */
export interface RoundRef {
  round: number;
  revision: number;
}

export interface ActionChoice {
  kind: ActionKind;
  ability_id?: string;
  emblem_tier?: string;
}

export interface StartBattleInput {
  encounter_id: string;
  ascended_id: string;
  preset_slot: number | null;
  mode: BattleMode;
  emblem_limit: string | null;
}

export interface EmblemPurchase {
  kind: "emblems";
  tier_id: string;
  quantity: number;
  price: number;
}

export interface CopyPurchase {
  kind: "copies";
  ascended_id: string;
  tier_id: string;
  copies_granted: number;
  price: number;
  slot: number;
  rotation: number;
  left: number;
}

export interface ShopOffer {
  slot: number;
  ascended_id: string;
  tier_id: string;
  copies_granted: number;
  stock: number;
  left: number;
  price: number;
  owned: boolean;
  owned_copies: number;
}

export interface ShopWindow {
  rotation: number;
  refreshes_at: number;
  /** Seconds to the next rotation when the answer was made; count down on this device's clock. */
  seconds_left: number;
  offers: ShopOffer[];
}

export interface Sale {
  kind: "sale";
  ascended_id: string;
  value: number;
  copies: number;
  tier_id: string;
}

export interface StarUp {
  kind: "star";
  ascended_id: string;
  tier_id: string;
  stars: number;
  stars_needed: number;
  essence_spent: number;
  copies: number;
  can_tier_up: boolean;
}

export interface TierUp {
  kind: "tier";
  ascended_id: string;
  from_tier_id: string;
  tier_id: string;
  stars: number;
}

const BASE = "/ascension";

/** A new Idempotency-Key for one user action. randomUUID exists only in
 * secure contexts (HTTPS or localhost); getRandomValues works everywhere. */
export function newIdempotencyKey(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}

const withKey = (key: string): Record<string, string> => ({ "Idempotency-Key": key });
const part = (id: string): string => encodeURIComponent(id);
const round = (at: RoundRef) => ({ round: at.round, revision: at.revision });

export class AscensionClient {
  private readonly http: HttpClient;
  constructor(http: HttpClient) { this.http = http; }
  catalog = () => this.http.request<Catalog>("GET", `${BASE}/catalog`);
  /** 404 (ApiError) until the account has chosen a starter. */
  profile = () => this.http.request<Profile>("GET", `${BASE}/profile`);
  createProfile = (starterAscendedId: string, key: string = newIdempotencyKey()) =>
    this.http.request<Profile>("POST", `${BASE}/profile`, { starter_ascended_id: starterAscendedId }, withKey(key));
  /** Deletes every Ascended, personality, preset, EMBLEM and Insignia. 404: no profile; 409: a battle is active. */
  resetProfile = (key: string = newIdempotencyKey()) =>
    this.http.request<{ reset: boolean }>("POST", `${BASE}/profile/reset`, { confirm: true }, withKey(key));
  personalities = (ascendedId: string, cursor: number | null = null, limit?: number) => {
    const query = new URLSearchParams();
    if (limit !== undefined) query.set("limit", String(limit));
    if (cursor !== null) query.set("cursor", String(cursor));
    const text = query.toString();
    return this.http.request<PersonalityPage>("GET", `${BASE}/ascendeds/${part(ascendedId)}/personalities${text ? `?${text}` : ""}`);
  };
  preset = (ascendedId: string, slot: number) => this.http.request<Preset>("GET", `${BASE}/ascendeds/${part(ascendedId)}/presets/${slot}`);
  savePreset = (ascendedId: string, slot: number, instanceIds: string[], key: string = newIdempotencyKey()) =>
    this.http.request<Preset>("PUT", `${BASE}/ascendeds/${part(ascendedId)}/presets/${slot}`, { instance_ids: instanceIds }, withKey(key));
  rollEncounter = (key: string = newIdempotencyKey()) =>
    this.http.request<EncounterPreview>("POST", `${BASE}/encounters`, undefined, withKey(key));
  encounter = (id: string) => this.http.request<EncounterPreview>("GET", `${BASE}/encounters/${part(id)}`);
  declineEncounter = (id: string, key: string = newIdempotencyKey()) =>
    this.http.request<EncounterPreview>("POST", `${BASE}/encounters/${part(id)}/decline`, undefined, withKey(key));
  startBattle = (input: StartBattleInput, key: string = newIdempotencyKey()) =>
    this.http.request<BattleView>("POST", `${BASE}/battles`, input, withKey(key));
  battle = (id: string) => this.http.request<BattleView>("GET", `${BASE}/battles/${part(id)}`);
  action = (id: string, at: RoundRef, choice: ActionChoice, key: string = newIdempotencyKey()) =>
    this.http.request<BattleView>("POST", `${BASE}/battles/${part(id)}/actions`, { ...round(at), action: choice }, withKey(key));
  emblem = (id: string, at: RoundRef, tier: string, key: string = newIdempotencyKey()) =>
    this.http.request<BattleView>("POST", `${BASE}/battles/${part(id)}/emblem`, { ...round(at), tier }, withKey(key));
  advance = (id: string, at: RoundRef, key: string = newIdempotencyKey()) =>
    this.http.request<BattleView>("POST", `${BASE}/battles/${part(id)}/advance`, round(at), withKey(key));
  /** emblemLimit null keeps the battle's own limit. */
  setMode = (id: string, at: RoundRef, mode: BattleMode, emblemLimit: string | null, key: string = newIdempotencyKey()) =>
    this.http.request<BattleView>(
      "POST",
      `${BASE}/battles/${part(id)}/mode`,
      { ...round(at), mode, ...(emblemLimit === null ? {} : { emblem_limit: emblemLimit }) },
      withKey(key),
    );
  forfeit = (id: string, key: string = newIdempotencyKey()) =>
    this.http.request<BattleView>("POST", `${BASE}/battles/${part(id)}/forfeit`, undefined, withKey(key));
  buyEmblems = (tier: string, quantity: number, key: string = newIdempotencyKey()) =>
    this.http.request<EmblemPurchase>("POST", `${BASE}/shop/purchases`, { kind: "emblem", tier, quantity }, withKey(key));
  shop = () => this.http.request<ShopWindow>("GET", `${BASE}/shop`);
  buyOffer = (rotation: number, slot: number, key: string = newIdempotencyKey()) =>
    this.http.request<CopyPurchase>("POST", `${BASE}/shop/purchases`, { kind: "copies", rotation, slot }, withKey(key));
  sellCopy = (ascendedId: string, key: string = newIdempotencyKey()) =>
    this.http.request<Sale>("POST", `${BASE}/ascendeds/${part(ascendedId)}/sales`, undefined, withKey(key));
  /** One star: a spare copy plus the tier's essence. */
  tree = (ascendedId: string) => this.http.request<TreeView>("GET", `${BASE}/ascendeds/${part(ascendedId)}/tree`);
  learnNode = (ascendedId: string, nodeId: string, key: string = newIdempotencyKey()) =>
    this.http.request<LearnResult>("POST", `${BASE}/ascendeds/${part(ascendedId)}/tree/${part(nodeId)}/learn`, undefined, withKey(key));
  saveLoadout = (ascendedId: string, abilities: string[], passive: string | null, key: string = newIdempotencyKey()) =>
    this.http.request<LoadoutResult>("PUT", `${BASE}/ascendeds/${part(ascendedId)}/loadout`, { abilities, passive }, withKey(key));

  addStar = (ascendedId: string, key: string = newIdempotencyKey()) =>
    this.http.request<StarUp>("POST", `${BASE}/ascendeds/${part(ascendedId)}/stars`, undefined, withKey(key));
  /** With enough stars, the next tier; the stars start again. */
  raiseTier = (ascendedId: string, key: string = newIdempotencyKey()) =>
    this.http.request<TierUp>("POST", `${BASE}/ascendeds/${part(ascendedId)}/tier`, undefined, withKey(key));
}

/** The client belongs to this app's session store, never a module singleton. */
export function useAscensionClient(): AscensionClient {
  const client = useSessionStore().client;
  if (!client) throw new Error("Game client is not configured");
  return client;
}
