/// <reference lib="dom" />
import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { PROFILE } from "../src/api/AscensionClient.fixtures.ts";

for (const viewport of [{ width: 1280, height: 720 }, { width: 390, height: 844 }]) {
  test(`only the main content scrolls at ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    const api = await installFakeApi(page);
    api.ascension.profile = { ...PROFILE };
    await page.goto("/#ticket=e2e-launch");
    await page.getByRole("button", { name: "Continue" }).click();
    const main = page.getByRole("main");
    const heading = page.getByRole("heading", { name: "Your collection" });
    const before = await heading.boundingBox();
    await page.screenshot({ path: testInfo.outputPath("collection.png") });
    await expect.poll(() => main.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
    await main.evaluate(el => { el.scrollTop = el.scrollHeight; });
    await expect.poll(() => main.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    expect(await heading.boundingBox()).toEqual(before);
    await expect(page.getByRole("tab", { name: "Battle", exact: true })).toBeVisible();
    await expect(page.getByRole("group", { name: "Filter by Ascension Type" })).toBeVisible();
    expect(await page.evaluate(() => ({
      pageScroll: document.scrollingElement!.scrollTop,
      pageOverflow: document.documentElement.scrollHeight > innerHeight,
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
    }))).toEqual({ pageScroll: 0, pageOverflow: false, horizontalOverflow: false });
  });
}

test("a first visit picks a starter, then the collection and the Battle tab open", async ({ page }) => {
  const api = await installFakeApi(page);
  await page.goto("/#ticket=e2e-launch");

  await expect(page.getByRole("button", { name: "New game" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue" })).toHaveCount(0);
  await page.getByRole("button", { name: "New game" }).click();
  await expect(page.getByRole("heading", { name: "Choose your first Ascended" })).toBeVisible();
  await page.getByRole("radio", { name: "Guardian" }).click();
  await page.getByRole("button", { name: "Start with Guardian" }).click();

  await expect(page.locator(".ascended-card")).toHaveCount(1);
  await expect(page.getByRole("tab", { name: "Battle", exact: true })).toBeEnabled();
  expect(api.ascension.keys).toHaveLength(1);
  expect(api.ascension.keys[0]).toMatch(/^[0-9a-f-]{32,36}$/);
  expect(api.unexpected).toEqual([]);
});
