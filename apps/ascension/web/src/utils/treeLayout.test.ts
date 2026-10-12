import { describe, expect, it } from "vitest";
import { layoutTree } from "./treeLayout";

describe("ability tree layout", () => {
  it("places prerequisites before descendants without overlapping nodes", () => {
    const result = layoutTree([{ id: "a", requires: [], y: 0 }, { id: "b", requires: [], y: 0 }, { id: "c", requires: ["a", "b"], y: -20 }]);
    expect(result.get("c")!.x).toBeGreaterThan(result.get("a")!.x + 156);
    expect(Math.abs(result.get("a")!.y - result.get("b")!.y)).toBeGreaterThanOrEqual(90);
    expect(Math.min(...Array.from(result.values()).map(p => p.y))).toBeGreaterThanOrEqual(0);
  });
});
