/// <reference lib="dom" />
import { expect, test, type Page } from "@playwright/test";
import { installFakeApi } from "./fakeApi";
import { PROFILE, ascendedInfo, ownedAscended } from "../src/api/AscensionClient.fixtures";

async function fits(page: Page) {
  const overflow = await page.evaluate(() => Array.from(document.querySelectorAll('*')).filter(el => el.getBoundingClientRect().right > innerWidth + 1 && getComputedStyle(el).position !== 'fixed').slice(0, 8).map(el => ({ tag: el.tagName, class: el.className, right: el.getBoundingClientRect().right })));
  expect.soft(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), JSON.stringify(overflow)).toBe(true);
  const sources = await page.locator('img[src^="/ascended/"]').evaluateAll(images => images.map(img => img.getAttribute("src")));
  expect(sources.every(src => src?.endsWith("/sprite_battle.webp"))).toBe(true);
}

for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
  test(`menu, collection, basket and active battle remain usable at ${viewport.width}px`, async ({ page }, testInfo) => {
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
    await expect(page.getByRole("button", { name: "Quick battle", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Continue", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Tavern/ })).toBeDisabled();
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath("menu.png"), fullPage: true });
    await fits(page);
    await page.getByRole("button", { name: "Collection", exact: true }).click();
    const guardian = page.getByRole("button", { name: "Guardian, details", exact: true });
    await guardian.focus();
    await guardian.press("Enter");
    await expect(page.getByRole("complementary", { name: "Selected Ascended" })).toContainText("Guardian");
    await expect(page.getByRole("button", { name: "Open details", exact: true })).toBeVisible();
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath("collection.png"), fullPage: true });
    if (viewport.width < 700) {
      await page.locator(".collection-inspector").scrollIntoViewIfNeeded();
      await page.screenshot({ animations: "disabled", path: testInfo.outputPath("collection-inspector.png") });
    }
    await fits(page);
    await page.getByRole("button", { name: "Main menu", exact: true }).click();
    await page.getByRole("button", { name: "Shop", exact: true }).click();
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
    await page.locator('[data-checkout]').click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(api.trades.filter(t => t.kind === "sale")).toHaveLength(0);
    await page.getByRole("dialog").getByRole("button", { name: /Confirm|Sell/, exact: false }).last().click();
    await expect.poll(() => api.trades.filter(t => t.kind === "sale").length).toBe(1);
    await page.getByRole("button", { name: "Main menu", exact: true }).click();
    await page.getByRole("button", { name: "Quick battle", exact: true }).click();
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
    await page.getByRole("button", { name: "Begin battle", exact: true }).click();
    await expect(page.locator(".arena")).toBeVisible();
    await expect(page.locator("button.action")).toHaveCount(4);
    await page.getByRole("main", { name: "Screen content", exact: true }).evaluate(el => { el.scrollTop = 0; });
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath("battle.png"), fullPage: true });
    if (viewport.width < 700) {
      await page.locator(".action-bar").scrollIntoViewIfNeeded();
      await page.screenshot({ animations: "disabled", path: testInfo.outputPath("battle-actions.png") });
    }
    await fits(page);
    await page.getByRole("button", { name: "Main menu", exact: true }).click();
    expect(api.battle?.status).toBe("active");
    await page.getByRole("button", { name: "Quick battle", exact: true }).click();
    await expect(page.locator(".arena")).toBeVisible();
    expect(api.battle?.status).toBe("active");
    expect(api.artRequests.every(path => path.endsWith("/sprite_battle.webp"))).toBe(true);
    expect(api.unexpected).toEqual([]);
  });

  test(`first visit selects a starter at ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    const api = await installFakeApi(page);
    await page.goto("/#ticket=e2e-launch");
    await page.getByRole("button", { name: "New game", exact: true }).click();
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
}
