import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("the sidebar collapses behind the header toggle on mobile and the profile menu remembers the theme", async ({ page }) => {
  const state = newState();
  await installFakeApi(page, state);
  await page.goto("/");
  const sidebar = page.getByRole("complementary", { name: "Treasury Admin" });
  const nav = page.getByRole("navigation", { name: "Treasury sections" });
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  await expect(nav.getByRole("link")).toHaveCount(5);
  await expect(nav.getByRole("link", { name: "Overview", exact: true })).toHaveAttribute("aria-current", "page");
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 800 });
    if (width >= 768) {
      await expect(sidebar).toBeVisible();
      expect((await sidebar.boundingBox())!.width).toBe(210);
    } else {
      await expect(sidebar).toBeHidden();
      await page.getByRole("button", { name: "Sidebar" }).click();
      await expect(sidebar).toBeVisible();
      expect((await sidebar.boundingBox())!.width).toBe(375);
      await page.getByRole("button", { name: "Sidebar" }).click();
      await expect(sidebar).toBeHidden();
    }
    expect(await page.evaluate<boolean>("document.documentElement.scrollWidth <= window.innerWidth")).toBe(true);
    const profile = page.getByRole("button", { name: "Profile", exact: true });
    await profile.click();
    await expect(page.getByRole("button", { name: "Log out", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "Log out", exact: true })).toHaveCount(0);
    await expect(profile).toBeFocused();
  }
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.getByRole("button", { name: "Profile", exact: true }).click();
  await page.locator(".header-popover select").selectOption("dark");
  await page.reload();
  expect(await page.evaluate<string>("document.documentElement.style.colorScheme")).toBe("dark");
  await nav.getByRole("link", { name: "Connections", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Connections", level: 1 })).toBeVisible();
  expect(state.unexpected).toEqual([]);
});
