/// <reference lib="dom" />
import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { CATALOG, PROFILE, ascendedInfo, ownedAscended } from "../src/api/AscensionClient.fixtures.ts";

for (const viewport of [{ width: 1280, height: 720 }, { width: 768, height: 720 }, { width: 390, height: 844 }]) {
  test(`squad preparation fits at ${viewport.width}px and respects reduced motion`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    const api = await installFakeApi(page);
    api.ascension.profile = {
      ...PROFILE,
      squad: ["guardian", "striker", "scout"],
      ascendeds: [ownedAscended("guardian", { level: 12, in_squad: true }), ownedAscended("striker", { level: 10, in_squad: true }),
        ownedAscended("scout", { level: 9, in_squad: true, fainted: true, faint_until: Date.now() / 1000 + 134 })],
    };
    await page.route("**/ascension/catalog", route => route.fulfill({ json: {
      ...CATALOG,
      ascendeds: [...CATALOG.ascendeds.map(info => info.id === "bruiser" ? { ...info, art: { ...info.art,
        main_card: "/ascended/bruiser/sprite_main_card.webp", preview_card: "/ascended/bruiser/sprite_preview_card.webp" } } : info),
        ascendedInfo("scout", { name: "Scout", art: { main_card: "/ascended/scout/sprite_main_card.webp", preview_card: "/ascended/scout/sprite_preview_card.webp", battle: null, focus: 50, focus_preview: 50, animation: null } })],
    } }));
    await page.goto("/#ticket=e2e-launch");
    await page.getByRole("tab", { name: "Battle", exact: true }).click();
    await page.getByRole("button", { name: "Look for a wild Ascended", exact: true }).click();
    await page.getByRole("button", { name: "Fight", exact: true }).click();
    const selected = page.getByRole("radiogroup", { name: "Your squad" }).getByRole("radio", { name: "Guardian" });
    await expect(selected).toHaveAttribute("aria-checked", "true");
    await expect(page.locator(".matchup .player .ascended-name")).toHaveText("Guardian");
    await expect(page.locator(".matchup .wild .ascended-name")).toHaveText("Bruiser");
    await expect(page.locator(".matchup .wild img")).toHaveAttribute("src", "/ascended/bruiser/sprite_main_card.webp");
    await page.getByRole("radio", { name: "Striker", exact: true }).click();
    await expect(page.locator(".matchup .player .ascended-name")).toHaveText("Striker");
    await selected.click();
    await expect(page.getByRole("radio", { name: "Scout", exact: true })).toHaveAttribute("aria-disabled", "true");
    await expect(page.locator("select[name='limit']")).toBeDisabled();
    const player = await page.locator(".matchup .player").boundingBox();
    const wild = await page.locator(".matchup .wild").boundingBox();
    expect(player!.y).toBe(wild!.y);
    expect(player!.x + player!.width).toBeLessThanOrEqual(wild!.x + 1);
    expect(await selected.evaluate(el => getComputedStyle(el).animationName)).toMatch(/^breathe(?:-|$)/);
    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(await selected.evaluate(el => getComputedStyle(el).animationDuration)).toBe("3.2s");
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    if (viewport.width > 700) await page.setViewportSize({ width: viewport.width, height: 1320 });
    await page.getByRole("main").evaluate(el => { el.scrollTop = 0; });
    await page.screenshot({ path: testInfo.outputPath("squad-setup.png"), fullPage: true });
    await page.getByRole("button", { name: "Begin battle", exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath("battle-plan.png"), fullPage: true });
    await page.getByRole("tab", { name: "Autonomous", exact: true }).click();
    await expect(page.getByRole("button", { name: "Begin battle", exact: true })).toBeDisabled();
    await page.locator("select[name='preset']").selectOption("2");
    await page.locator("select[name='limit']").selectOption("rare");
    await expect(page.getByRole("button", { name: "Begin battle", exact: true })).toBeEnabled();
    expect(api.unexpected).toEqual([]);
  });

  test(`only the main content scrolls at ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    const api = await installFakeApi(page);
    api.ascension.profile = { ...PROFILE };
    await page.goto("/#ticket=e2e-launch");
    await expect(page.getByRole("heading", { name: "Your collection" })).toBeVisible();
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
    await expect(page.getByRole("button", { name: "Continue", exact: true })).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "Shop", exact: true })).toHaveCount(0);
    const wallet = page.getByRole("button", { name: "Open shop, 100 Insignia" });
    const walletBox = await wallet.boundingBox();
    const helpBox = await page.getByRole("button", { name: "How to play", exact: true }).boundingBox();
    const settingsBox = await page.getByRole("button", { name: "Settings", exact: true }).boundingBox();
    expect(walletBox!.x).toBeLessThan(helpBox!.x);
    expect(helpBox!.x).toBeLessThan(settingsBox!.x);
    expect(walletBox!.y).toBe(helpBox!.y);
    expect(walletBox!.y).toBe(settingsBox!.y);
    await wallet.click();
    await expect(page.getByRole("heading", { name: "The forge shop" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Battle", exact: true })).toHaveAttribute("tabindex", "0");
    await page.getByRole("button", { name: "How to play", exact: true }).click();
    const help = page.getByRole("dialog", { name: "Keep the fire going" });
    await expect(help).toBeVisible();
    await help.getByRole("button", { name: "Ready to play" }).click();
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    const settings = page.getByRole("dialog", { name: "Settings", exact: true });
    await settings.getByRole("button", { name: "Reset progress", exact: true }).click();
    const reset = page.getByRole("dialog", { name: "Reset all Ascension progress?" });
    await expect(reset.getByRole("button", { name: "Reset progress", exact: true })).toBeDisabled();
    await reset.getByRole("textbox", { name: "Type RESET to confirm" }).fill("RESET");
    await reset.getByRole("button", { name: "Reset progress", exact: true }).click();
    await expect(page.getByRole("button", { name: "New game", exact: true })).toBeVisible();
    await expect(settings).not.toBeVisible();
    expect(api.unexpected).toEqual([]);
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

  await expect(page.locator(".squad-card")).toHaveCount(1);
  await expect(page.getByRole("tab", { name: "Battle", exact: true })).toBeEnabled();
  expect(api.ascension.keys).toHaveLength(1);
  expect(api.ascension.keys[0]).toMatch(/^[0-9a-f-]{32,36}$/);
  await page.getByRole("tab", { name: "Battle", exact: true }).click();
  await page.getByRole("button", { name: "Look for a wild Ascended", exact: true }).click();
  await page.getByRole("button", { name: "Fight", exact: true }).click();
  const squad = page.getByRole("radiogroup", { name: "Your squad" });
  await expect(squad.getByRole("radio", { name: "Guardian", exact: true })).toHaveAttribute("aria-checked", "true");
  await expect(squad.locator(".empty-slot")).toHaveCount(4);
  await expect(page.locator(".start-form .matchup .player .ascended-name")).toHaveText("Guardian");
  await expect(page.getByRole("button", { name: "Begin battle", exact: true })).toBeEnabled();
  expect(api.unexpected).toEqual([]);
});
