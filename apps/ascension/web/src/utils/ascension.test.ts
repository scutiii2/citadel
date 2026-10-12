import { describe, expect, it } from "vitest";
import { CATALOG } from "../api/AscensionClient.fixtures";
import { effectText, statusText, abilityEffect, actionTone, describeAction, describeEvent, formatCountdown, passiveText, tierStanding, titleCase } from "./ascension";

const NAMES = { player: "Guardian", wild: "Bruiser" };

describe("passiveText and abilityEffect", () => {
  it("writes every shipped passive kind as a sentence", () => {
    expect(passiveText("defense_extension", { protected_attacks: 2, rounds: 2 })).toBe("Defense shields 2 attacks for 2 rounds.");
    expect(passiveText("defense_extension", {})).toBe("Defense shields 1 attack for 1 round.");
    expect(passiveText("low_hp_attack_bonus", { hp_below: 0.5, power_fraction: 0.2 })).toBe(
      "Below 50% HP, attacks deal extra damage equal to 20% of its Power.",
    );
    expect(passiveText("battle_start_speed", { power_fraction: 0.5 })).toBe("At battle start, gains Speed equal to 50% of its Power.");
    expect(passiveText("defense_rating_bonus", { power_fraction: 0.5 })).toContain("50% of its Power");
    expect(passiveText("attack_bonus_vs_defense", { power_fraction: 0.25 })).toContain("25% of its Power");
    expect(passiveText("support_duration_bonus", { rounds: 1 })).toBe("Support effects last 1 round longer.");
    expect(passiveText("cooldown_reduction", { rounds: 1, minimum: 1 })).toBe("Ability cooldowns are 1 round shorter, down to 1.");
  });

  it("falls back to the kind's name, and writes an ability's effect line", () => {
    expect(passiveText("something_new", {})).toBe("Something new");
    expect(abilityEffect({ category: "ATTACK", percentage: 150, cooldown: 1 })).toBe("Attack 150% · cd 1");
  });
});

describe("ascension helpers", () => {
  it("draws the three strongest tiers as top and the one below as middle", () => {
    expect(CATALOG.tiers.map((t) => tierStanding(CATALOG.tiers, t.id))).toEqual(["low", "low", "middle", "top", "top", "top"]);
    expect(tierStanding(CATALOG.tiers, "unknown")).toBe("low");
  });

  it("writes ids as words", () => {
    expect(titleCase("knocked_out")).toBe("Knocked out");
    expect(titleCase("AGGRESSIVE")).toBe("Aggressive");
    expect(titleCase("rare")).toBe("Rare");
  });

  it("formats countdowns, rounding up", () => {
    expect(formatCountdown(4.2)).toBe("0:05");
    expect(formatCountdown(90)).toBe("1:30");
    expect(formatCountdown(3723)).toBe("1:02:03");
    expect(formatCountdown(-3)).toBe("0:00");
  });

  it("puts round-log events and actions in words", () => {
    expect(describeEvent({ type: "attack", side: "wild", damage: 12, protected: false, target_hp: 68 }, NAMES)).toBe(
      "Bruiser hits for 12; Guardian has 68 HP left",
    );
    expect(describeEvent({ type: "capture_attempt", side: "player", emblem: "rare", chance: 0.25, success: true }, NAMES)).toBe(
      "Guardian throws a Rare EMBLEM (25%): caught",
    );
    expect(describeEvent({ type: "order", first: "wild", chance_player_first: 0.4 }, NAMES)).toBe("Bruiser moves first");
    expect(describeEvent({ type: "something_new" }, NAMES)).toBe("Something new");
    expect(describeAction("ability:guardian_strike", [{ id: "guardian_strike", name: "Strike" }])).toBe("Strike");
    expect(describeAction("flee", [])).toBe("Flee");
  });
});

describe("actionTone", () => {
  it("colours abilities by category and flee and catch by themselves", () => {
    expect(actionTone("attack", "ATTACK")).toBe("attack");
    expect(actionTone("ability:guard", "Defense")).toBe("defense");
    expect(actionTone("ability:boost", "SUPPORT")).toBe("support");
    expect(actionTone("flee", "FLEE")).toBe("flee");
    expect(actionTone("catch", "CATCH")).toBe("catch");
    expect(actionTone("ability:odd", "MYSTERY")).toBe("other");
  });
});

describe("effects in words", () => {
  it("writes each effect kind", () => {
    expect(effectText(undefined)).toBe("");
    expect(effectText([])).toBe("");
    expect(effectText([{ kind: "heal", percentage: 50 }])).toBe("Heals 50% of power");
    expect(effectText([{ kind: "regen", percentage: 25, rounds: 3 }])).toBe("Regenerates 25% for 3 rounds");
    expect(effectText([{ kind: "bleed", percentage: 20, rounds: 1 }])).toBe("Bleeds 20% for 1 round");
    expect(effectText([{ kind: "slow", percentage: 30, rounds: 2 }, { kind: "weaken", percentage: 10, rounds: 2 }])).toBe(
      "Slows 30% for 2 rounds, Weakens 10% for 2 rounds",
    );
    expect(effectText([{ kind: "exposed", percentage: 40, rounds: 2 }])).toBe("Exposes 40% for 2 rounds");
    expect(effectText([{ kind: "mark", name: "prey", rounds: 3 }])).toBe("Marks prey for 3 rounds");
    expect(effectText([{ kind: "mark", name: "soaked", rounds: 2, target: "self" }])).toBe("Gains the soaked mark for 2 rounds");
    expect(effectText([{ kind: "cleanse" }, { kind: "ward", rounds: 2 }])).toBe("Cleanses, Wards one lethal hit for 2 rounds");
  });

  it("appends effects to the ability line only when there are some", () => {
    expect(abilityEffect({ category: "ATTACK", percentage: 150, cooldown: 1 })).toBe("Attack 150% · cd 1");
    expect(abilityEffect({ category: "ATTACK", percentage: 150, cooldown: 1, effects: [{ kind: "bleed", percentage: 20, rounds: 3 }] })).toBe(
      "Attack 150% · cd 1 · Bleeds 20% for 3 rounds",
    );
  });

  it("writes statuses and the new passives and events", () => {
    expect(statusText({ id: "bleed", amount: 5, rounds_left: 2 })).toBe("bleeding 5 a round, 2 rounds left");
    expect(statusText({ id: "slow", amount: -10, rounds_left: 1 })).toBe("slowed by 10, 1 round left");
    expect(statusText({ id: "weaken", amount: -4, rounds_left: 2 })).toBe("weakened by 4, 2 rounds left");
    expect(statusText({ id: "exposed", amount: 20, rounds_left: 2 })).toBe("exposed, defense down 20, 2 rounds left");
    expect(statusText({ id: "regen", amount: 7, rounds_left: 3 })).toBe("regenerating 7 a round, 3 rounds left");
    expect(statusText({ id: "ward", amount: 0, rounds_left: 2 })).toBe("warded, 2 rounds left");
    expect(statusText({ id: "mark:prey", amount: 0, rounds_left: 1 })).toBe("marked prey, 1 round left");
    expect(passiveText("attack_bonus_vs_marked", { mark: "prey", power_fraction: 0.2 })).toBe(
      "Attacks deal extra damage equal to 20% of its Power against a target marked prey.",
    );
    expect(passiveText("heal_bonus", { fraction: 0.5 })).toBe("Heals are 50% stronger.");
    expect(passiveText("heal_bonus", { fraction: 0.5, hp_below: 0.5 })).toBe("Below 50% HP, heals are 50% stronger.");
    expect(describeEvent({ type: "heal", side: "player", amount: 12 }, NAMES)).toBe("Guardian heals 12");
    expect(describeEvent({ type: "status", side: "player", target: "wild", status: "bleed", amount: 5, rounds: 2 }, NAMES)).toBe(
      "Guardian puts bleed on Bruiser for 2 rounds",
    );
    expect(describeEvent({ type: "status", side: "player", target: "wild", status: "mark:prey", amount: 0, rounds: 1 }, NAMES)).toBe(
      "Guardian puts a prey mark on Bruiser for 1 round",
    );
    expect(describeEvent({ type: "cleanse", side: "wild", removed: ["bleed", "slow"] }, NAMES)).toBe("Bruiser cleanses bleed, slow");
    expect(describeEvent({ type: "tick", side: "wild", kind: "bleed", amount: 5, hp: 30 }, NAMES)).toBe("Bruiser bleeds for 5; 30 HP left");
    expect(describeEvent({ type: "tick", side: "player", kind: "regen", amount: 7, hp: 60 }, NAMES)).toBe("Guardian recovers 7; 60 HP");
    expect(describeEvent({ type: "ward_triggered", side: "player" }, NAMES)).toBe("Guardian is saved by a ward at 1 HP");
  });
});
