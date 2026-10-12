import type { PersonalityInfo, PersonalityRule } from "../api/AscensionClient";
import { titleCase } from "./ascension";

export const personalityCategory = (id: string): string => id === "FEAR" ? "Flee" : titleCase(id);
const number = (n: number): string => String(Math.round(n * 100) / 100);
const percent = (n: unknown): string => `${number(Number(n) * 100)}%`;

function condition(key: string, value: number | string | boolean): string {
  switch (key) {
    case "own_hp_under": return `HP is below ${percent(value)}`;
    case "lead_under": return Number(value) === 0 ? "behind the opponent" : `lead is below ${percent(value)}`;
    case "lead_over": return `lead is above ${percent(value)}`;
    case "rage_over": return `rage is above ${percent(value)}`;
    case "confidence_over": return `confidence is above ${percent(value)}`;
    case "nerves_over": return `nerves are above ${percent(value)}`;
    case "hit_taken_over": return `last damage taken exceeds ${percent(value)} of max HP`;
    case "streak_over": return `action streak is longer than ${value}`;
    case "round_under": return `round is below ${value}`;
    case "round_over": return `round is above ${value}`;
    case "enemy_low": return value ? "opponent has low HP" : "opponent does not have low HP";
    case "enemy_last_is": return `opponent last chose ${personalityCategory(String(value))}`;
    default: return `${titleCase(key)}: ${value}`;
  }
}

function ruleDescription(rule: PersonalityRule, tier: number): string {
  const strength = tier / 3;
  const effects: string[] = [];
  for (const [category, factor] of Object.entries(rule.multiply ?? {})) {
    effects.push(`${personalityCategory(category)} preference ×${number(1 + (factor - 1) * strength)}`);
  }
  if (rule.chaos) effects.push(`shift ${percent(rule.chaos * strength)} toward less likely action categories`);
  if (rule.counter) effects.push("favor a counter to the opponent’s last action");
  if (rule.copy_enemy) effects.push("favor the opponent’s last action category");
  if (rule.break_streak) effects.push("break long action streaks by favoring a different category");
  if (rule.stay) effects.push(`favor staying in the same category (×${number(1 + (rule.stay - 1) * strength)})`);
  if (rule.repeat) effects.push(`repeat-action weight ×${number(rule.repeat)} per consecutive repeat`);
  if (rule.pick_by_percentage) effects.push(`favor ${rule.pick_by_percentage === "high" ? "higher" : "lower"}-percentage abilities within a category`);
  const when = Object.entries(rule.when).map(([key, value]) => condition(key, value)).join(" and ");
  return `${when ? `When ${when}: ` : ""}${effects.join("; ")}.`;
}

/** Describe catalog behavior at this instance's tier, without inventing fixed action odds. */
export function personalityDescription(personality: PersonalityInfo | undefined, tier: number): string {
  if (!personality) return "Personality effects are unavailable. Reload the catalog to see details.";
  const lines: string[] = [];
  if (personality.categories.length) {
    lines.push(`Favors ${personality.categories.map(personalityCategory).join(" and ")}. Adds ${tier} preference weight to each when leading.`);
  }
  lines.push(...(personality.rules ?? []).map(rule => ruleDescription(rule, tier)));
  if (!lines.length) return personality.rules === undefined
    ? "Conditional effects are unavailable from this server."
    : "No extra action preference. Decisions follow the battle situation.";
  return lines.join(" ");
}
