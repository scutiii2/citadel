import { describe, expect, it } from "vitest";
import { layoutTree } from "./treeLayout";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ascendedDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../../ascended");

describe("ability tree layout", () => {
  it("spreads four foundation paths around the central hub", () => {
    const nodes = [0,1,2,3].map(i => ({ id: `root${i}`, requires: [], y: i * 100 }));
    const result = layoutTree(nodes);
    const points = [...result.positions.values()];
    expect(result.branches).toHaveLength(4);
    expect(points.some(p => p.x < result.center.x && p.y < result.center.y)).toBe(true);
    expect(points.some(p => p.x > result.center.x && p.y < result.center.y)).toBe(true);
    expect(points.some(p => p.x > result.center.x && p.y > result.center.y)).toBe(true);
    expect(points.some(p => p.x < result.center.x && p.y > result.center.y)).toBe(true);
  });
  it("keeps a descendant outward and identifies a shared capstone", () => {
    const result = layoutTree([{ id: "a", requires: [], y: 0 }, { id: "b", requires: [], y: 100 }, { id: "next", requires: ["a"], y: 0 }, { id: "cap", requires: ["next", "b"], y: 0 }]);
    const distance = (id: string) => Math.hypot(result.positions.get(id)!.x-result.center.x, result.positions.get(id)!.y-result.center.y);
    expect(distance("next")).toBeGreaterThan(distance("a"));
    expect(result.sharedIds.has("cap")).toBe(true);
  });
  it("groups declared branches instead of creating a path per root", () => {
    const result = layoutTree([{ id: "a", requires: [], y: 0, branch: "aya" }, { id: "p", requires: [], y: 20, branch: "aya" }, { id: "w", requires: [], y: 40, branch: "wolf" }]);
    expect(result.branches.map(b => b.id)).toEqual(["aya", "wolf"]);
  });
  it("recognizes cross-path prerequisites even when the capstone has its own named branch", () => {
    const result = layoutTree([{ id: "a", requires: [], y: 0, branch: "aya" }, { id: "w", requires: [], y: 40, branch: "wolf" }, { id: "cap", requires: ["a", "w"], y: 80, branch: "dog" }]);
    expect(result.sharedIds.has("cap")).toBe(true);
    expect(result.branches.map(b => b.id)).toEqual(["aya", "wolf", "dog"]);
  });
  for (const id of readdirSync(ascendedDir, { withFileTypes: true }).filter(entry => entry.isDirectory()).map(entry => entry.name)) {
    it(`places every ${id} node inside the canvas without overlapping names or the hub`, () => {
      const nodes = JSON.parse(readFileSync(resolve(ascendedDir, id, "tree.json"), "utf8")).nodes.map((n: { requires?: string[] }) => ({ requires: [], ...n }));
      const result = layoutTree(nodes);
      const points = [...result.positions.values()];
      expect(points).toHaveLength(nodes.length);
      for (let i = 0; i < points.length; i++) {
        const p = points[i]!;
        expect(p.x).toBeGreaterThanOrEqual(78);
        expect(p.y).toBeGreaterThanOrEqual(36);
        expect(p.x + 78).toBeLessThanOrEqual(result.width);
        expect(p.y + 80).toBeLessThanOrEqual(result.height);
        expect(Math.abs(p.x-result.center.x) >= 150 || Math.abs(p.y-result.center.y) >= 160).toBe(true);
        for (const q of points.slice(i+1)) expect(Math.abs(p.x-q.x) >= 160 || Math.abs(p.y-q.y) >= 120).toBe(true);
      }
    });
  }
  it("handles an empty tree", () => {
    const result = layoutTree([]);
    expect(result.positions.size).toBe(0);
    expect(Number.isFinite(result.width)).toBe(true);
  });
});
