import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { CATALOG, PROFILE, ascendedInfo, ownedAscended } from "../src/api/AscensionClient.fixtures";
import type { TreeNodeState, TreeView } from "../src/api/AscensionClient";
import { installFakeApi } from "./fakeApi";

const spec = JSON.parse(readFileSync(new URL("../../ascended/striker/catalog.json", import.meta.url), "utf8"));
const definitions = JSON.parse(readFileSync(new URL("../../ascended/striker/tree.json", import.meta.url), "utf8")).nodes;
const configuration = JSON.parse(readFileSync(new URL("../../configs/ascension_catalog.json", import.meta.url), "utf8"));
const personalities = configuration.personalities;

test("Twoychi uses main card art and a saved preset across the detail tabs", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const api = await installFakeApi(page);
  const character = JSON.parse(readFileSync(new URL("../../ascended/twoychi/catalog.json", import.meta.url), "utf8"));
  const nodes = JSON.parse(readFileSync(new URL("../../ascended/twoychi/tree.json", import.meta.url), "utf8")).nodes;
  api.ascension.profile = { ...PROFILE, essences: { unique: 15 }, squad: ["twoychi"], ascendeds: [ownedAscended("twoychi", { name: "Twoychi", in_squad: true, default_preset_slot: 2, level: 7, tier_id: "unique", xp: 664, xp_needed: 700, copies: 2, stars_needed: 3, star_essence_cost: 3, next_tier_id: 'royal', can_star_up: true })] };
  const pool = [{ id: "p1", type: "AGGRESSIVE", tier: 2 }, { id: "p2", type: "RECKLESS", tier: 1 }, { id: "p3", type: "BOLD", tier: 1 }];
  const art = { main_card: "/ascended/twoychi/sprite_main_card.webp", preview_card: "/ascended/twoychi/sprite_preview_card.webp", battle: "/ascended/twoychi/sprite_battle.webp", focus: 50, focus_preview: 50, animation: null };
  await page.route("**/ascension/catalog", route => route.fulfill({ json: { ...CATALOG, personalities, ascendeds: [ascendedInfo("twoychi", { ...character, art })] } }));
  await page.route("**/ascended/twoychi/sprite_*.webp", route => route.fulfill({ contentType: "image/webp", body: readFileSync(new URL("../../ascended/twoychi/" + new URL(route.request().url()).pathname.split("/").pop(), import.meta.url)) }));
  await page.route("**/ascension/ascendeds/twoychi/personalities*", route => route.fulfill({ json: { items: pool.slice(0, 1), next_cursor: null } }));
  await page.route("**/ascension/ascendeds/twoychi/presets/*", route => {
    const slot = Number(new URL(route.request().url()).pathname.split("/").pop());
    return route.fulfill({ json: { ascended_id: "twoychi", slot, instance_ids: pool.map(p => p.id), personalities: pool } });
  });
  await page.route("**/ascension/ascendeds/twoychi/default-preset", route => {
    const { slot } = route.request().postDataJSON();
    return route.fulfill({ json: { ascended_id: "twoychi", slot } });
  });
  await page.route("**/ascension/ascendeds/twoychi/tree", route => route.fulfill({ json: {
    ascended_id: "twoychi", level: 7, essences: { common: 33 },
    slots: ["p1", "p2", "a1", "a2", "a3", "a4"].map(id => ({ id, kind: id.startsWith("p") ? "passive" : "ability", branches: null })),
    loadout: { a1: "twoychi_tidecall" },
    nodes: nodes.map((node: any) => ({ kind: "ability", name: node.id, requires: [], root: false, unlock_level: 1, cost: null, ...character.abilities.find((a: any) => a.id === node.id), ...node, state: node.root ? "learned" : "locked", reason: "Requirements not met" })),
  } }));
  await page.goto("/#ticket=e2e-launch");
  await page.getByRole("tab", { name: "Collection", exact: true }).click();
  await page.locator(".squad-card").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.locator(".detail-portrait")).toHaveAttribute("src", "/ascended/twoychi/sprite_main_card.webp");
  await expect(dialog.locator(".preset-preview li")).toHaveCount(3);
  await expect(dialog.locator(".preset-preview")).toContainText("Reckless");
  await dialog.getByRole("button", { name: "Use preset 3 as battle default", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Use preset 3 as battle default", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(await dialog.locator(".title").evaluate(el => getComputedStyle(el).textDecorationLine)).toBe("none");
  await page.screenshot({ animations: "disabled", path: testInfo.outputPath("twoychi-overview.png") });
  await dialog.getByRole('tab', { name: 'Progression', exact: true }).click();
  await expect(dialog.getByRole('heading', { name: 'Path to Royal', exact: true })).toBeVisible();
  await expect(dialog.locator('.progression-resources')).toContainText('Spare copies2');
  await expect(dialog.getByRole('button', { name: 'Add a star', exact: true })).toBeEnabled();
  await page.screenshot({ animations: 'disabled', path: testInfo.outputPath('twoychi-progression.png') });
  await dialog.getByRole("tab", { name: "Personalities", exact: true }).click();
  await expect(dialog.locator(".preset-inspector h4")).toHaveText("Preset 3");
  await expect(dialog.locator(".selected-personalities strong")).toHaveCount(3);
  await expect(dialog.getByRole("tablist", { name: "Preset slot" })).toHaveCount(1);
  await page.screenshot({ animations: "disabled", path: testInfo.outputPath("twoychi-personality.png") });
  await dialog.getByRole("tab", { name: "Ability tree", exact: true }).click();
  await dialog.getByRole("button", { name: "Fit tree", exact: true }).click();
  await expect(dialog.locator(".slots .slot")).toHaveCount(6);
  await page.screenshot({ animations: "disabled", path: testInfo.outputPath("twoychi-tree.png") });
  expect(api.unexpected).toEqual([]);
});

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
      loadout: { a1: "striker_flurry", a2: "striker_battle_focus", a3: "striker_brace", p1: "striker_passive" },
      nodes: definitions.map((n: Partial<TreeNodeState> & { id: string }) => {
        const ability = spec.abilities.find((a: { id: string }) => a.id === n.id);
        return { kind: "ability", name: "Low HP Attack Bonus", unlock_level: 1, cost: null, requires: [], ...ability, ...n,
          ...(n.id === "striker_passive" ? { kind: "passive", passive: spec.passive } : {}),
          state: learned.has(n.id) ? "learned" : n.id === "striker_scorching_edge" ? "learnable" : "locked", reason: learned.has(n.id) ? null : "Requirements not met" };
      }),
    };
    await page.route("**/ascension/ascendeds/striker/tree", route => route.fulfill({ json: tree }));
    await page.goto("/#ticket=e2e-launch");
    await page.getByRole("tab", { name: "Collection", exact: true }).click();
    await page.locator(".ascended-card").click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.locator('.head .battle-status')).toHaveText('Ready for battle');
    await expect(dialog.locator('.progression-drawer, .copy-summary')).toHaveCount(0);
    expect(await dialog.locator('.title').evaluate(el => getComputedStyle(el, '::after').content)).toBe('none');
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`overview-${width}.png`) });
    await dialog.getByRole('tab', { name: 'Progression', exact: true }).click();
    await expect(dialog.getByRole('tabpanel', { name: 'Progression', exact: true })).toBeVisible();
    await expect(dialog.locator('.progression-resources')).toContainText('Spare copies4');
    await expect(dialog.locator(".progression-panel .em-essence")).toHaveCount(2);
    await expect.poll(() => dialog.locator(".progression-panel .em-essence").evaluateAll(images => images.every(img => (img as HTMLImageElement).naturalWidth > 0))).toBe(true);
    expect(await dialog.locator('.progression-tab').evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`progression-${width}.png`) });
    await dialog.getByRole('button', { name: 'Add a star', exact: true }).scrollIntoViewIfNeeded();
    await expect(dialog.getByRole('button', { name: 'Add a star', exact: true })).toBeEnabled();
    await dialog.getByRole("tab", { name: "Personalities", exact: true }).click();
    await expect(dialog.locator(".personality-description").first()).toContainText("3 preference weight");
    await expect(dialog.locator(".personality-description").last()).toContainText("HP is below 50%");
    await dialog.locator("input[role=switch]").first().check();
    await expect(dialog.getByRole("button", { name: "Save preset", exact: true })).toBeEnabled();
    await expect(dialog.locator('.head .battle-status')).toHaveText('Ready for battle');
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`personalities-${width}.png`) });
    await dialog.getByRole("tab", { name: "Ability tree", exact: true }).click();
    await expect(dialog.locator(".origin-hub")).toHaveText('');
    expect(await dialog.locator('.hub-portrait').evaluate(el => parseFloat(getComputedStyle(el).borderRadius))).toBeGreaterThan(0);
    await expect(dialog.locator('[data-node="striker_scorching_edge"] polygon')).toHaveCount(1);
    await expect(dialog.locator('[data-node="striker_passive"] circle.node-outline')).toHaveCount(1);
    await dialog.getByRole("button", { name: "Fit tree", exact: true }).click();
    expect(await dialog.locator('.canvas').evaluate(canvas => {
      const pointAt = (path: SVGPathElement, end: boolean) => {
        const p = path.getPointAtLength(end ? path.getTotalLength() : 0);
        return new DOMPoint(p.x, p.y).matrixTransform(path.getScreenCTM()!);
      };
      const touches = (id: string, p: DOMPoint) => {
        const shape = canvas.querySelector<SVGGeometryElement>(`.tree-node[data-node="${id}"] .node-outline`)!;
        return shape.isPointInStroke(p.matrixTransform(shape.getScreenCTM()!.inverse()));
      };
      const broken = Array.from(canvas.querySelectorAll<SVGPathElement>('.tree-line')).filter(path =>
        !touches(path.dataset.from!, pointAt(path, false)) || !touches(path.dataset.to!, pointAt(path, true)));
      const origin = canvas.querySelector('.hub-portrait')!.getBoundingClientRect();
      const brokenRoots = Array.from(canvas.querySelectorAll<SVGPathElement>('.origin-line')).filter(path => {
        const startsAtOrigin = path.dataset.originStart === 'true';
        const p = pointAt(path, !startsAtOrigin);
        const onBorder = Math.min(Math.abs(p.x - origin.left), Math.abs(p.x - origin.right), Math.abs(p.y - origin.top), Math.abs(p.y - origin.bottom)) < 2;
        return !onBorder || !touches(path.dataset.to!, pointAt(path, startsAtOrigin));
      });
      return broken.length + brokenRoots.length;
    })).toBe(0);
    await dialog.locator('[data-node="striker_scorching_edge"]').click();
    await expect(dialog.locator(".node-detail")).toContainText("Flurry learned");
    await expect(dialog.locator(".node-detail")).toContainText("You have 12");
    await expect(dialog.locator(".node-detail")).toContainText("Bleeds 20% for 3 rounds");
    await expect(dialog.locator(".tree-line.highlighted")).toHaveCount(2);
    await expect(dialog.locator('.node-name, .node-state, .equipped-mark')).toHaveCount(0);
    expect(await dialog.locator('.tree-node').first().evaluate(el => ({ background: getComputedStyle(el).backgroundImage, shadow: getComputedStyle(el).boxShadow }))).toEqual({ background: 'none', shadow: 'none' });
    expect(await dialog.locator('.node-symbol').first().evaluate(el => getComputedStyle(el).borderTopWidth)).toBe('0px');
    await expect(dialog.locator('[data-node="striker_scorching_edge"] .node-level')).toContainText(String(definitions.find((n: TreeNodeState) => n.id === "striker_scorching_edge").unlock_level));
    const equipped = dialog.locator('[data-node="striker_flurry"]');
    await expect(equipped).toHaveClass(/equipped/);
    expect(await equipped.locator('.node-shape').evaluate(el => getComputedStyle(el).filter)).toContain('drop-shadow');
    expect(await dialog.locator('[data-node="striker_rending_strike"] .node-shape').evaluate(el => getComputedStyle(el).filter)).toBe('none');
    expect(await dialog.locator('.tree-line.equipped').first().evaluate(el => getComputedStyle(el).filter)).toContain('drop-shadow');
    expect(await dialog.locator('.tree-line:not(.equipped)').first().evaluate(el => getComputedStyle(el).filter)).toBe('none');
    expect(await dialog.locator('.origin-line.equipped').first().evaluate(el => getComputedStyle(el).filter)).toContain('drop-shadow');
    await equipped.hover();
    await expect(equipped.locator('.node-tooltip')).toBeVisible();
    await expect(equipped.locator('.node-tooltip')).toHaveText('Flurry');
    await dialog.getByRole('button', { name: 'Fit tree', exact: true }).hover();
    await expect(equipped.locator('.node-tooltip')).toBeHidden();
    expect(await dialog.locator('[data-node="striker_sunsteel_cleave"] .node-icon').evaluate(el => getComputedStyle(el).filter)).toBe('grayscale(1)');
    await expect.poll(() => dialog.locator('.node-icon').evaluateAll(images => images.every(img => (img as HTMLImageElement).naturalWidth > 0))).toBe(true);
    await dialog.getByRole("button", { name: "Zoom in", exact: true }).click();
    await expect(dialog.locator(".node-detail button.learn")).toBeEnabled();
    expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    if (width === 1440) await dialog.getByRole("button", { name: "Fit tree", exact: true }).click();
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`tree-${width}.png`) });
    await dialog.getByRole("button", { name: "Fit tree", exact: true }).click();
    await dialog.locator('[data-node="striker_sunsteel_cleave"]').click();
    await expect(dialog.locator(".tree-line.shared-link.highlighted")).toHaveCount(6);
    for (const control of ['slider', 'wheel']) {
      await dialog.getByRole('button', { name: 'Zoom in', exact: true }).click();
      if (control === 'slider') {
        await dialog.locator('input[aria-label="Zoom"]').evaluate(el => {
          const input = el as HTMLInputElement;
          input.value = input.min;
          input.dispatchEvent(new Event('input', { bubbles: true }));
        });
      } else {
        await dialog.locator('.scroll').evaluate(el => {
          const box = el.getBoundingClientRect();
          for (let i = 0; i < 40; i++) el.dispatchEvent(new WheelEvent('wheel', { deltaY: 100, clientX: box.left + 10, clientY: box.top + 10, bubbles: true }));
        });
      }
      await expect.poll(() => dialog.locator('.scroll').evaluate(el => {
        const view = el.getBoundingClientRect(), canvas = el.querySelector('.canvas')!.getBoundingClientRect();
        return canvas.left >= view.left - 1 && canvas.right <= view.right + 1 && canvas.top >= view.top - 1 && canvas.bottom <= view.bottom + 1;
      })).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    expect(api.unexpected).toEqual([]);
  });
}
