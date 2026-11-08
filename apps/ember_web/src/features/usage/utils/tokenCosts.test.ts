import { describe, expect, it } from "vitest";
import { TOKEN_COSTS, withTokenCost, type CostedSetting } from "./tokenCosts";

describe("tokenCosts", () => {
  it("has a note for every chat setting", () => {
    const settings: CostedSetting[] = ["terse", "independent", "plan", "planLean", "askTools", "chime", "notifications", "suggestions", "liveTokens", "contextPanel", "contextAccuracy"];
    expect(Object.keys(TOKEN_COSTS).sort()).toEqual([...settings].sort());
    for (const key of settings) expect(TOKEN_COSTS[key].length).toBeGreaterThan(10);
  });

  it("says plainly which settings cost nothing and which add tokens", () => {
    expect(TOKEN_COSTS.chime).toMatch(/^No token cost/);
    expect(TOKEN_COSTS.askTools).toMatch(/^No token cost/);
    expect(TOKEN_COSTS.plan).toMatch(/200 input tokens/);
    expect(TOKEN_COSTS.planLean).toMatch(/35 input tokens/);
  });

  it("puts the cost after the hint in a tooltip", () => {
    expect(withTokenCost("Show a checklist", "plan")).toBe(`Show a checklist. ${TOKEN_COSTS.plan}`);
  });
});
