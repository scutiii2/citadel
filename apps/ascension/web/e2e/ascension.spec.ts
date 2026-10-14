/// <reference lib="dom" />
import { expect, test, type Page } from "@playwright/test";
import { installFakeApi } from "./fakeApi";
import { PROFILE, ascendedInfo, ownedAscended, battleView, fighter } from "../src/api/AscensionClient.fixtures";

async function fits(page: Page) {
  const overflow = await page.evaluate(() => Array.from(document.querySelectorAll('*')).filter(el => el.getBoundingClientRect().right > innerWidth + 1 && getComputedStyle(el).position !== 'fixed').slice(0, 8).map(el => ({ tag: el.tagName, class: el.className, right: el.getBoundingClientRect().right })));
  expect.soft(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), JSON.stringify(overflow)).toBe(true);
  const sources = await page.locator('img[src^="/ascended/"]').evaluateAll(images => images.map(img => img.getAttribute("src")));
  expect(sources.every(src => src?.endsWith("/sprite_battle.webp"))).toBe(true);
}

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`collection, basket and active battle remain usable at ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    const api = await installFakeApi(page);
    api.ascension.profile = { ...structuredClone(PROFILE), insignia: 300,
      squad: ["guardian", "striker", "scout"], ascendeds: [
        ownedAscended("guardian", { in_squad: true, copies: 3, sale_value: 25 }),
        ownedAscended("striker", { in_squad: true, level: 8 }),
        ownedAscended("scout", { in_squad: true, fainted: true, faint_until: Date.now() / 1000 + 134 }),
        ownedAscended("channeler", { level: 6, tier_id: "unique", copies: 2 }),
      ] };
    api.catalog.ascendeds.push(ascendedInfo("scout"), ascendedInfo("channeler"));
    api.encounter = { ...api.encounter, ascended_id: "channeler", name: "Channeler", tier_id: "unique" };
    await page.goto("/#ticket=e2e-launch");
    await expect(page.getByRole("tab", { name: "Collection", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("button", { name: "Continue", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Tavern/ })).toBeDisabled();
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath("menu.png"), fullPage: true });
    await fits(page);
    await page.getByRole("tab", { name: "Collection", exact: true }).click();
    const guardian = page.getByRole("button", { name: "Guardian, details", exact: true });
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath("collection.png"), fullPage: true });
    await guardian.focus();
    await guardian.press("Enter");
    await expect(page.getByRole("dialog")).toContainText("Guardian");
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath("overview.png"), fullPage: true });
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await fits(page);
    await page.getByRole("button", { name: /Open shop/ }).click();
    await page.locator('[data-offer="0"] button[data-add]').click();
    await page.locator('[data-basket] input').fill("2");
    await page.locator('[data-tier="common"] button[data-add]').click();
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath("shop.png"), fullPage: true });
    if (viewport.width < 700) {
      await page.locator('[data-checkout]').scrollIntoViewIfNeeded();
      await page.screenshot({ animations: "disabled", path: testInfo.outputPath("shop-basket.png") });
    }
    await fits(page);
    await page.locator('[data-checkout]').click();
    await expect.poll(() => api.trades.length).toBe(3);
    expect(api.trades.map(t => t.kind)).toEqual(["copies", "copies", "emblems"]);
    await expect(page.locator('[data-basket] input')).toHaveCount(0);
    await page.locator('[data-mode="sell"]').click();
    await page.locator('[data-sell="guardian"] button[data-add]').click();
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath("shop-sell.png"), fullPage: true });
    await page.locator('[data-checkout]').click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(api.trades.filter(t => t.kind === "sale")).toHaveLength(0);
    await page.getByRole("dialog").getByRole("button", { name: /Confirm|Sell/, exact: false }).last().click();
    await expect.poll(() => api.trades.filter(t => t.kind === "sale").length).toBe(1);
    await page.getByRole("tab", { name: "Battle", exact: true }).click();
    await page.getByRole("button", { name: "Look for a wild Ascended", exact: true }).click();
    await page.getByRole("button", { name: "Fight", exact: true }).click();
    await expect(page.getByRole("radio", { name: "Scout", exact: true })).toHaveAttribute("aria-disabled", "true");
    await page.getByRole("radio", { name: "Striker", exact: true }).click();
    await expect(page.locator(".matchup .player .ascended-name")).toHaveText("Striker");
    await page.getByRole("radio", { name: "Guardian", exact: true }).click();
    await page.getByRole("tab", { name: "Autonomous", exact: true }).click();
    await expect(page.getByRole("button", { name: "Begin battle", exact: true })).toBeDisabled();
    await page.locator("select[name='preset']").selectOption("2");
    await page.locator("select[name='limit']").selectOption("rare");
    await expect(page.getByRole("button", { name: "Begin battle", exact: true })).toBeEnabled();
    await page.getByRole("tab", { name: "Manual", exact: true }).click();
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath("battle-plan.png"), fullPage: true });
    if (viewport.width < 700) {
      await page.locator(".begin-battle").scrollIntoViewIfNeeded();
      await page.screenshot({ animations: "disabled", path: testInfo.outputPath("battle-plan-controls.png") });
    }
    await fits(page);
    const pick = await page.locator('.matchup .player').boundingBox();
    const opponent = await page.locator('.matchup .wild').boundingBox();
    expect(pick!.x).toBeLessThan(opponent!.x);
    await expect(page.locator('.matchup .arena')).toHaveCount(1);
    await page.getByRole("button", { name: "Begin battle", exact: true }).click();
    await expect(page.locator(".arena")).toBeVisible();
    await expect(page.locator("button.action")).toHaveCount(5);
    await expect(page.locator('button.action.unavailable')).toHaveCount(1);
    await expect(page.locator('button.action.unavailable')).toBeDisabled();
    await expect(page.locator('button.action.unavailable')).toContainText('Requires level 5');
    await expect(page.getByRole("button", { name: "Skip animation" })).toHaveCount(0);
    await expect(page.locator(".battle-side .controls")).toBeVisible();
    await expect(page.locator('.arena .player .passives')).toContainText('Defense rating rises by 40% of its Power.');
    await expect(page.locator('.arena .wild .passives')).toContainText('Below 50% HP');
    expect(await page.locator('.arena .fighter').evaluateAll(fighters => fighters.every(f =>
      f.querySelector('.passives')!.getBoundingClientRect().top >= f.querySelector('.stats')!.getBoundingClientRect().bottom))).toBe(true);
    const arenaHeight = (await page.locator('.arena').boundingBox())!.height;
    await page.locator('.round-log').evaluate(el => { (el as HTMLElement).style.minHeight = '700px'; });
    expect((await page.locator('.arena').boundingBox())!.height).toBe(arenaHeight);
    await page.locator('.round-log').evaluate(el => { (el as HTMLElement).style.minHeight = ''; });
    if (viewport.width > 900) {
      const arena = await page.locator('.arena').boundingBox();
      const actions = await page.locator('.action-bar').boundingBox();
      expect(actions!.y - (arena!.y + arena!.height)).toBeLessThanOrEqual(8);
    }
    expect(await page.locator('.arena .fighter').evaluateAll(fighters => fighters.every(fighter => {
      const health = fighter.querySelector('.health')!.getBoundingClientRect();
      const art = fighter.querySelector('.art')!.getBoundingClientRect();
      return health.top >= art.top && health.bottom <= art.bottom;
    }))).toBe(true);
    if (viewport.width <= 900) { const move = await page.locator(".action-bar").boundingBox(); const log = await page.locator(".round-log").boundingBox(); expect(move!.y + move!.height).toBeLessThanOrEqual(log!.y); }
    await page.getByRole("main", { name: "Screen content", exact: true }).evaluate(el => { el.scrollTop = 0; });
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath("battle.png"), fullPage: true });
    if (viewport.width < 700) {
      await page.locator(".action-bar").scrollIntoViewIfNeeded();
      await page.screenshot({ animations: "disabled", path: testInfo.outputPath("battle-actions.png") });
    }
    await fits(page);
    await page.getByRole("tab", { name: "Collection", exact: true }).click();
    expect(api.battle?.status).toBe("active");
    await page.getByRole("tab", { name: "Battle", exact: true }).click();
    await expect(page.locator(".arena")).toBeVisible();
    expect(api.battle?.status).toBe("active");
    expect(api.artRequests.every(path => path.endsWith("/sprite_battle.webp"))).toBe(true);
    expect(api.unexpected).toEqual([]);
  });

  test(`first visit selects a starter at ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    const api = await installFakeApi(page);
    await page.goto("/#ticket=e2e-launch");
    await page.getByRole("radio", { name: "Striker", exact: true }).click();
    await expect(page.getByRole("button", { name: "Start with Striker", exact: true })).toBeEnabled();
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath("starter.png"), fullPage: true });
    if (viewport.width < 700) {
      await page.locator(".start").scrollIntoViewIfNeeded();
      await page.screenshot({ animations: "disabled", path: testInfo.outputPath("starter-inspector.png") });
    }
    await fits(page);
    await page.getByRole("button", { name: "Start with Striker", exact: true }).click();
    await expect(page.locator(".squad-card")).toHaveCount(1);
    expect(api.ascension.keys).toHaveLength(1);
    expect(api.ascension.keys[0]).toMatch(/^[0-9a-f-]{32,36}$/);
    expect(api.artRequests.every(path => path.endsWith("/sprite_battle.webp"))).toBe(true);
    expect(api.unexpected).toEqual([]);
  });
  for (const kind of ["captured", "won"] as const) {
    test(`battle ${kind} result restores the three-panel composition at ${viewport.width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize(viewport);
      const api = await installFakeApi(page);
      api.catalog.ascendeds.push(ascendedInfo("channeler"));
      api.ascension.profile = { ...structuredClone(PROFILE), active_battle: "b1", ascendeds: [ownedAscended("guardian"), ownedAscended("striker"), ownedAscended("scout")] };
      api.battle = battleView({ status: "terminal", phase: "terminal", wild: fighter("channeler", { name: "Channeler" }), result: {
        kind, xp: 120, insignia: 80, essence: 6, essence_tier_id: "unique",
        ...(kind === "captured" ? { copies_granted: 1, revealed_personalities: [{ id: "p1", type: "CAUTIOUS", tier: 1 }, { id: "p2", type: "AGGRESSIVE", tier: 2 }] } : {}),
        squad_xp: [{ ascended_id: "striker", name: "Striker", xp: 30, level_before: 3, level_after: 3 }, { ascended_id: "scout", name: "Scout", xp: 30, level_before: 3, level_after: 4 }],
      } });
      await page.goto("/#ticket=e2e-launch");
      await page.getByRole("tab", { name: "Battle", exact: true }).click();
      await expect(page.locator(".result-scene")).toBeVisible();
      await expect(page.locator(".reward")).toHaveCount(kind === "captured" ? 4 : 3);
      await expect(page.locator(".squad-xp li")).toHaveCount(3);
      await page.screenshot({ animations: "disabled", path: testInfo.outputPath("result.png"), fullPage: true });
      await fits(page);
      if (viewport.width === 1440) {
        const scene = await page.locator(".result-scene").boundingBox();
        const rewards = await page.locator(".rewards").boundingBox();
        const details = await page.locator(".result-details").boundingBox();
        expect(scene!.x).toBeLessThan(rewards!.x);
        expect(rewards!.x).toBeLessThan(details!.x);
        expect(Math.abs(scene!.y - rewards!.y)).toBeLessThan(2);
      }
      api.ascension.profile.active_battle = null;
      await page.getByRole("button", { name: "Back to encounters", exact: true }).click();
      await expect(page.locator(".encounter-panel")).toBeVisible();
      expect(api.unexpected).toEqual([]);
    });
  }
}

test("touch-first devices receive the PC-only notice", async ({ browser }) => {
  const context = await browser.newContext({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await installFakeApi(page);
  await page.goto("/#ticket=e2e-launch");
  await expect(page.getByRole("alert")).toContainText("Ascension is PC only");
  await expect(page.locator(".shell")).toHaveCount(0);
  await context.close();
});
