import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("the sidebar collapses behind the header toggle on mobile and the profile menu remembers the theme", async ({ page }) => {
  const state = newState();
  await installFakeApi(page, state);
  await page.goto("/admin/roles");
  const sidebar = page.getByRole("complementary", { name: "Portcullis Admin" });
  const nav = page.getByRole("navigation", { name: "Admin sections" });
  await expect(page.getByRole("heading", { name: "Roles & permissions", level: 1 })).toBeVisible();
  await expect(nav.getByRole("link")).toHaveCount(5);
  await expect(nav.getByRole("link", { name: "Roles & permissions", exact: true })).toHaveAttribute("aria-current", "page");
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 800 });
    if (width >= 768) {
      await expect(sidebar).toBeVisible();
      expect((await sidebar.boundingBox())!.width).toBe(210);
    } else {
      // Mobile: hidden until the header toggle discloses it above the content.
      await expect(sidebar).toBeHidden();
      await page.getByRole("button", { name: "Expand sidebar" }).click();
      await expect(sidebar).toBeVisible();
      const box = (await sidebar.boundingBox())!;
      expect(box.width).toBe(375);
      expect(box.y).toBeLessThan(200);
      await page.getByRole("button", { name: "Collapse sidebar" }).click();
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
  await page.locator(".header-popover select").selectOption("light");
  expect(await page.evaluate<string>("document.documentElement.style.colorScheme")).toBe("light");
  await page.locator(".header-popover select").selectOption("dark");
  await page.reload();
  expect(await page.evaluate<string>("document.documentElement.style.colorScheme")).toBe("dark");
  await page.getByRole("button", { name: "Profile", exact: true }).click();
  await expect(page.locator(".header-popover select")).toHaveValue("dark");
  await page.keyboard.press("Escape");
  await nav.getByRole("link", { name: "Accounts", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Accounts", level: 1 })).toBeVisible();
  expect(state.unexpected).toEqual([]);
});
