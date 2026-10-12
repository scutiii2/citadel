import type { EffectInfo, Status, AbilityInfo, BattleEvent, FighterAbility, ResultKind, TierInfo } from "../api/AscensionClient";

/** How a tier badge is drawn: the three strongest tiers with the accent, the
 * one below them in full text colour, the rest muted. The tier name is always
 * written, so colour is never the only signal. */
export type TierStanding = "top" | "middle" | "low";

export function tierStanding(tiers: readonly Pick<TierInfo, "id">[], tierId: string): TierStanding {
  const index = tiers.findIndex((t) => t.id === tierId);
  if (index === -1) return "low";
  const fromTop = tiers.length - 1 - index;
  if (fromTop <= 2) return "top";
  return fromTop === 3 ? "middle" : "low";
}

/** "knocked_out" -> "Knocked out", "AGGRESSIVE" -> "Aggressive". */
export function titleCase(id: string): string {
  const text = id
    .split("_")
    .filter(Boolean)
    .map((word) => word.toLowerCase())
    .join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function count(value: unknown, fallback: number, noun: string): string {
  const n = typeof value === "number" ? value : fallback;
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

/** A passive in one sentence, from its catalog kind and params (Ascension'
 * passives.py). An unknown kind falls back to its name. */
export function passiveText(kind: string, params: Record<string, unknown>): string {
  switch (kind) {
    case "attack_bonus_vs_marked":
      return `Attacks deal extra damage equal to ${percent(params.power_fraction)} of its Power against a target marked ${String(params.mark)}.`;
    case "heal_bonus":
      return `${params.hp_below === undefined ? "" : `Below ${percent(params.hp_below)} HP, `}${params.hp_below === undefined ? "Heals" : "heals"} are ${percent(params.fraction)} stronger.`;
    case "defense_extension":
      return `Defense shields ${count(params.protected_attacks, 1, "attack")} for ${count(params.rounds, 1, "round")}.`;
    case "low_hp_attack_bonus":
      return `Below ${percent(params.hp_below)} HP, attacks deal extra damage equal to ${percent(params.power_fraction)} of its Power.`;
    case "battle_start_speed":
      return `At battle start, gains Speed equal to ${percent(params.power_fraction)} of its Power.`;
    case "defense_rating_bonus":
      return `Defense rating rises by ${percent(params.power_fraction)} of its Power.`;
    case "attack_bonus_vs_defense":
      return `Attacks deal extra damage equal to ${percent(params.power_fraction)} of its Power against a defending target.`;
    case "support_duration_bonus":
      return `Support effects last ${count(params.rounds, 1, "round")} longer.`;
    case "cooldown_reduction":
      return `Ability cooldowns are ${count(params.rounds, 1, "round")} shorter, down to ${params.minimum ?? 1}.`;
    default:
      return titleCase(kind);
  }
}

function rounds(effect: EffectInfo): string {
  return count(effect.rounds, 1, "round");
}

/** An ability's effects in words, joined by commas; empty when it has none. */
export function effectText(effects: readonly EffectInfo[] | undefined): string {
  return (effects ?? [])
    .map((e) => {
      switch (e.kind) {
        case "heal": return `Heals ${e.percentage}% of power`;
        case "regen": return `Regenerates ${e.percentage}% for ${rounds(e)}`;
        case "bleed": return `Bleeds ${e.percentage}% for ${rounds(e)}`;
        case "slow": return `Slows ${e.percentage}% for ${rounds(e)}`;
        case "weaken": return `Weakens ${e.percentage}% for ${rounds(e)}`;
        case "exposed": return `Exposes ${e.percentage}% for ${rounds(e)}`;
        case "mark": return e.target === "self" ? `Gains the ${e.name} mark for ${rounds(e)}` : `Marks ${e.name} for ${rounds(e)}`;
        case "cleanse": return "Cleanses";
        case "ward": return `Wards one lethal hit for ${rounds(e)}`;
        default: return titleCase(e.kind);
      }
    })
    .join(", ");
}

/** One status on a fighter, in words. */
export function statusText(status: Status): string {
  const left = `${count(status.rounds_left, 1, "round")} left`;
  if (status.id.startsWith("mark:")) return `marked ${status.id.slice("mark:".length)}, ${left}`;
  switch (status.id) {
    case "bleed": return `bleeding ${status.amount} a round, ${left}`;
    case "slow": return `slowed by ${Math.abs(status.amount)}, ${left}`;
    case "weaken": return `weakened by ${Math.abs(status.amount)}, ${left}`;
    case "exposed": return `exposed, defense down ${status.amount}, ${left}`;
    case "regen": return `regenerating ${status.amount} a round, ${left}`;
    case "ward": return `warded, ${left}`;
    default: return `${titleCase(status.id)}, ${left}`;
  }
}

/** An ability's effect line: "Attack 150% · cd 1". */
export function abilityEffect(ability: Pick<AbilityInfo, "category" | "percentage" | "cooldown" | "effects">): string {
  const base = `${titleCase(ability.category)} ${ability.percentage}% · cd ${ability.cooldown}`;
  const extra = effectText(ability.effects);
  return extra ? `${base} · ${extra}` : base;
}

/** Seconds as m:ss (h:mm:ss from an hour), rounded up so 0:00 means done. */
export function formatCountdown(seconds: number): string {
  const total = Math.max(0, Math.ceil(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

export const RESULT_LABELS: Record<ResultKind, string> = {
  won: "You won",
  knocked_out: "Your Ascended was knocked out",
  captured: "Captured",
  escaped: "You escaped",
  wild_escaped: "The wild Ascended escaped",
  forfeited: "You forfeited",
};

export interface SideNames {
  player: string;
  wild: string;
}

function sideName(side: unknown, names: SideNames): string {
  return side === "wild" ? names.wild : names.player;
}

function percent(value: unknown): string {
  return `${Math.round(Number(value) * 100)}%`;
}

/** One line of the round log for an engine event (Ascension's engine.py). */
export function describeEvent(event: BattleEvent, names: SideNames): string {
  const who = sideName(event.side, names);
  switch (event.type) {
    case "order":
      return `${sideName(event.first, names)} moves first`;
    case "attack": {
      const target = sideName(event.side === "wild" ? "player" : "wild", names);
      const defended = event.protected ? " (defended)" : "";
      return `${who} hits for ${String(event.damage)}${defended}; ${target} has ${String(event.target_hp)} HP left`;
    }
    case "defense":
      return `${who} braces (defense ${String(event.rating)})`;
    case "support":
      return `${who} raises ${String(event.stat)} by ${String(event.amount)}`;
    case "flee":
      return `${who} tries to flee (${percent(event.chance)}) and ${event.success ? "gets away" : "fails"}`;
    case "catch_counters_flee":
      return `${who} stops ${sideName(event.target, names)} from fleeing`;
    case "catch_ignored":
      return `${who} tries to catch, to no effect`;
    case "capture_attempt":
      return `${who} throws a ${titleCase(String(event.emblem))} EMBLEM (${percent(event.chance)}): ${event.success ? "caught" : "it broke free"}`;
    case "heal":
      return `${who} heals ${String(event.amount)}`;
    case "status": {
      const target = sideName(event.target, names);
      const id = String(event.status);
      const what = id.startsWith("mark:") ? `a ${id.slice("mark:".length)} mark` : id;
      return `${who} puts ${what} on ${target} for ${count(event.rounds, 1, "round")}`;
    }
    case "cleanse":
      return `${who} cleanses ${(event.removed as string[]).join(", ") || "nothing"}`;
    case "tick":
      return event.kind === "bleed"
        ? `${who} bleeds for ${String(event.amount)}; ${String(event.hp)} HP left`
        : `${who} recovers ${String(event.amount)}; ${String(event.hp)} HP`;
    case "ward_triggered":
      return `${who} is saved by a ward at 1 HP`;
    default:
      return titleCase(event.type);
  }
}

/** A history action key in words: "ability:<id>" -> the ability's name. */
export function describeAction(key: string, abilities: readonly Pick<FighterAbility, "id" | "name">[]): string {
  if (key.startsWith("ability:")) {
    const id = key.slice("ability:".length);
    return abilities.find((a) => a.id === id)?.name ?? titleCase(id);
  }
  return titleCase(key);
}

/** What colour family an action belongs to, as ActionBar paints it: abilities by their
 * category, flee and catch by themselves, anything unexpected as "other". */
export type ActionTone = "attack" | "defense" | "support" | "flee" | "catch" | "other";

export function actionTone(key: string, category: string): ActionTone {
  if (key === "flee" || key === "catch") return key;
  const tone = category.toLowerCase();
  return tone === "attack" || tone === "defense" || tone === "support" ? tone : "other";
}

