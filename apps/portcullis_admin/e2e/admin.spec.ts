import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("the Ember rail moves to the bottom on mobile and remembers the theme", async ({ page }) => {
  const state = newState();
  await installFakeApi(page, state);
  await page.goto("/admin/roles");
  const rail = page.getByRole("complementary", { name: "Ember Admin" });
  const nav = page.getByRole("navigation", { name: "Admin sections" });
  await expect(nav.getByRole("link")).toHaveCount(4);
  await expect(nav.getByRole("link", { name: "Roles & permissions", exact: true })).toHaveAttribute("aria-current", "page");
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 800 });
    const box = await rail.boundingBox();
    expect(box).not.toBeNull();
    if (width >= 768) {
      expect(box!.width).toBe(52);
      expect(box!.x).toBe(0);
    } else {
      expect(box!.height).toBe(52);
      expect(box!.y + box!.height).toBe(800);
    }
    expect(await page.evaluate<boolean>("document.documentElement.scrollWidth <= window.innerWidth")).toBe(true);
    const account = page.getByRole("button", { name: "root - account menu", exact: true });
    await expect(account).toBeVisible();
    await account.click();
    await expect(page.getByRole("menuitem", { name: "Log out", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
  }
  await page.getByRole("button", { name: "root - account menu", exact: true }).click();
  await page.getByRole("menuitem", { name: /^Theme\s+System$/ }).click();
  await page.getByRole("menuitem", { name: /^Theme\s+Light$/ }).click();
  expect(await page.evaluate<string>("document.documentElement.style.colorScheme")).toBe("dark");
  await page.reload();
  await page.getByRole("button", { name: "root - account menu", exact: true }).click();
  await expect(page.getByRole("menuitem", { name: /^Theme\s+Dark$/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await nav.getByRole("link", { name: "Accounts", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Accounts", exact: true })).toBeVisible();
  expect(state.unexpected).toEqual([]);
});
