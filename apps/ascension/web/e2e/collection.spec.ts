import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi";
import { PROFILE, ownedAscended } from "../src/api/AscensionClient.fixtures";

for (const viewport of [{ width: 1440, height: 900 }, { width: 768, height: 1024 }, { width: 390, height: 844 }]) {
  test("collection configuration responds to orientation at " + viewport.width + "px", async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    const api = await installFakeApi(page);
    api.ascension.profile = { ...structuredClone(PROFILE), ascendeds: [ownedAscended("guardian"), ownedAscended("striker", { tier_id: "rare" })] };
    await page.goto("/#ticket=e2e-launch");
    const rail = page.getByRole("complementary", { name: "Collection filters" });
    const content = page.locator(".collection-main");
    const toggle = rail.getByRole("button", { name: "Configuration", exact: true });
    const search = rail.getByRole("searchbox", { name: "Search collection" });
    await expect(rail).toBeVisible();
    const surface = await rail.evaluate(el => ({ border: getComputedStyle(el).borderTopWidth, background: getComputedStyle(el).backgroundImage, shadow: getComputedStyle(el).boxShadow }));
    expect(surface.border).toBe('0px');
    expect(surface.shadow).toBe('none');
    expect(surface.background).toBe(viewport.height > viewport.width ? 'none' : 'linear-gradient(90deg, rgba(4, 21, 34, 0.6), rgba(0, 0, 0, 0))');
    if (viewport.height > viewport.width) {
      await expect(toggle).toBeVisible();
      await expect(search).toBeHidden();
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-expanded", "true");
      await expect(search).toBeVisible();
      const railBox = (await rail.boundingBox())!;
      const contentBox = (await content.boundingBox())!;
      expect(railBox.y + railBox.height).toBeLessThanOrEqual(contentBox.y);
    } else {
      await expect(toggle).toBeHidden();
      await expect(search).toBeVisible();
      expect((await rail.boundingBox())!.x).toBeLessThan((await content.boundingBox())!.x);
    }
    expect(await rail.locator(".configuration-content").evaluate(el => Array.from(el.children).map(child => child.className))).toEqual(["filter-label", "filter-group type-filters", "filter-group tier-filters", "filter-group grouping-filters", "uncollected"]);
    await expect(rail.locator(".rail-count")).toHaveText("2/4 Acquired");
    await rail.locator('[data-tier-filter="rare"]').click();
    await expect(page.locator(".ascended-card")).toHaveCount(1);
    await rail.getByRole("radio", { name: "Ascension Type", exact: true }).check();
    await expect(page.locator(".collected-zone .group[data-type=enchant]")).toBeVisible();
    await expect(rail.locator(".rail-count")).toHaveText("2/4 Acquired");
    if (viewport.height > viewport.width) {
      await toggle.click();
      await expect(search).toBeHidden();
      await toggle.click();
      await expect(rail.locator('[data-tier-filter="rare"]')).toHaveAttribute("aria-pressed", "true");
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("collection-configuration.png") });
  });
}
