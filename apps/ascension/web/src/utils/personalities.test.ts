import { describe, expect, it } from "vitest";
import { personalityDescription } from "./personalities";

describe("personality descriptions", () => {
  it("explains tier weight without presenting it as an action probability", () => {
    const text = personalityDescription({ id: "BOLD", categories: ["ATTACK", "SUPPORT"] }, 2);
    expect(text).toContain("Attack and Support");
    expect(text).toContain("2 preference weight");
    expect(text).not.toContain("2%");
  });
  it("describes a conditional rule at the instance's tier strength", () => {
    const text = personalityDescription({ id: "RECKLESS", categories: [], rules: [{ when: { own_hp_under: 0.5 }, multiply: { ATTACK: 1.6, DEFENSE: 0.7, FEAR: 0.5 } }] }, 2);
    expect(text).toContain("HP is below 50%");
    expect(text).toContain("Attack preference ×1.4");
    expect(text).toContain("Flee preference ×0.67");
  });
  it("distinguishes no bias from missing rule data", () => {
    expect(personalityDescription({ id: "STOIC", categories: [], rules: [] }, 1)).toContain("No extra action preference");
    expect(personalityDescription({ id: "CUNNING", categories: [] }, 1)).toContain("unavailable");
  });
});
