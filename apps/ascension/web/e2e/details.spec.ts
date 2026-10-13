import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { CATALOG, PROFILE, ascendedInfo, ownedAscended } from "../src/api/AscensionClient.fixtures";
import type { TreeNodeState, TreeView } from "../src/api/AscensionClient";
import { installFakeApi } from "./fakeApi";

const spec = JSON.parse(readFileSync(new URL("../../ascended/striker/catalog.json", import.meta.url), "utf8"));
const definitions = JSON.parse(readFileSync(new URL("../../ascended/striker/tree.json", import.meta.url), "utf8")).nodes;
const configuration = JSON.parse(readFileSync(new URL("../../configs/ascension_catalog.json", import.meta.url), "utf8"));
const personalities = configuration.personalities;

for (const width of [1440, 768, 375]) {
  test(`Ascended details show copies, personality effects and ability requirements at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    const api = await installFakeApi(page);
    api.ascension.profile = { ...PROFILE, essences: { common: 12, rare: 8 }, ascendeds: [ownedAscended("striker", { copies: 4, level: 14, tier_id: "rare", stars: 1, stars_needed: 2, next_tier_id: "unique", star_essence_cost: 2, xp: 620, xp_needed: 1000, can_star_up: true })] };
    await page.route("**/ascension/catalog", route => route.fulfill({ json: { ...CATALOG, tiers: configuration.tiers, personality_off_mood_factor: 0.5, personalities, ascendeds: [ascendedInfo("striker", { ...spec, art: ascendedInfo("striker").art })] } }));
    await page.route("**/ascended/striker/sprite_*.webp", route => {
      const name = new URL(route.request().url()).pathname.split("/").pop()!;
      return route.fulfill({ contentType: "image/webp", body: readFileSync(new URL(`../../ascended/striker/${name}`, import.meta.url)) });
    });
    await page.route("**/ascension/ascendeds/striker/personalities*", route => route.fulfill({ json: { items: [{ id: "p1", type: "AGGRESSIVE", tier: 3 }, { id: "p2", type: "RECKLESS", tier: 2 }], next_cursor: null } }));
    await page.route("**/ascension/ascendeds/striker/presets/*", route => route.fulfill({ json: { ascended_id: "striker", slot: 1, instance_ids: [] } }));
    const learned = new Set(["striker_rending_strike", "striker_battle_focus", "striker_brace", "striker_passive", "striker_flurry"]);
    const tree: TreeView = {
      ascended_id: "striker", level: 14, essences: { common: 12, rare: 8 },
      slots: [{ id: "a1", kind: "ability", branches: null }, { id: "a2", kind: "ability", branches: null },
        { id: "a3", kind: "ability", branches: null }, { id: "p1", kind: "passive", branches: null }],
      loadout: { a1: "striker_rending_strike", a2: "striker_battle_focus", a3: "striker_brace", p1: "striker_passive" },
      nodes: definitions.map((n: Partial<TreeNodeState> & { id: string }) => {
        const ability = spec.abilities.find((a: { id: string }) => a.id === n.id);
        return { kind: "ability", name: "Low HP Attack Bonus", unlock_level: 1, cost: null, requires: [], ...ability, ...n,
          ...(n.id === "striker_passive" ? { kind: "passive", passive: spec.passive } : {}),
          state: learned.has(n.id) ? "learned" : n.id === "striker_scorching_edge" ? "learnable" : "locked", reason: learned.has(n.id) ? null : "Requirements not met" };
      }),
    };
    await page.route("**/ascension/ascendeds/striker/tree", route => route.fulfill({ json: tree }));
    await page.goto("/#ticket=e2e-launch");
    await page.getByRole("button", { name: "Collection", exact: true }).click();
    await page.locator(".ascended-card").click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.locator(".copy-summary")).toContainText("4 spare copies");
    await expect(dialog.locator(".copy-summary")).toBeVisible();
    await dialog.getByRole("tab", { name: "Personalities", exact: true }).click();
    await expect(dialog.locator(".personality-description").first()).toContainText("3 preference weight");
    await expect(dialog.locator(".personality-description").last()).toContainText("HP is below 50%");
    await dialog.locator("input[role=switch]").first().check();
    await expect(dialog.getByRole("button", { name: "Save preset", exact: true })).toBeEnabled();
    await expect(dialog.locator(".copy-summary")).toBeVisible();
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`personalities-${width}.png`) });
    await dialog.getByRole("tab", { name: "Ability tree", exact: true }).click();
    await expect(dialog.locator(".origin-hub")).toContainText("Striker");
    await expect(dialog.locator('[data-node="striker_scorching_edge"] polygon')).toHaveCount(1);
    await expect(dialog.locator('[data-node="striker_passive"] circle.node-outline')).toHaveCount(1);
    await dialog.locator('[data-node="striker_scorching_edge"]').click();
    await expect(dialog.locator(".node-detail")).toContainText("Flurry learned");
    await expect(dialog.locator(".node-detail")).toContainText("You have 12");
    await expect(dialog.locator(".node-detail")).toContainText("Bleeds 20% for 3 rounds");
    await expect(dialog.locator(".tree-line.highlighted")).toHaveCount(2);
    await dialog.getByRole("button", { name: "Hide names", exact: true }).click();
    await expect(dialog.locator('[data-node="striker_scorching_edge"] .node-name')).toBeHidden();
    await dialog.getByRole("button", { name: "Show names", exact: true }).click();
    await dialog.getByRole("button", { name: "Zoom in", exact: true }).click();
    await expect(dialog.locator(".node-detail button.learn")).toBeEnabled();
    expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    if (width === 1440) await dialog.getByRole("button", { name: "Fit tree", exact: true }).click();
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`tree-${width}.png`) });
    await dialog.locator('[data-node="striker_sunsteel_cleave"]').click();
    await expect(dialog.locator(".tree-line.shared-link.highlighted")).toHaveCount(6);
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    expect(api.unexpected).toEqual([]);
  });
}
