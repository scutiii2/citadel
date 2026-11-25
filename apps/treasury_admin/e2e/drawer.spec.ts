import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("the drawer expands, scrolls its own body, keeps the footer reachable and discards after asking", async ({ page }) => {
  const state = newState();
  await installFakeApi(page, state);
  await page.goto("/connections");
  await page.locator("tbody .admin-row-button").filter({ hasText: "reports" }).click();
  const drawer = page.getByRole("dialog", { name: "Connection reports", exact: true });
  await drawer.getByRole("button", { name: "Edit", exact: true }).click();
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 600 });
    expect(await page.evaluate<string>("getComputedStyle(document.querySelector('dialog.record-drawer .drawer-body')).overflowY")).toBe("auto");
    expect(await page.evaluate<boolean>("document.documentElement.scrollHeight <= window.innerHeight")).toBe(true);
    const footer = (await drawer.locator(".drawer-footer").boundingBox())!;
    expect(footer.y + footer.height).toBeLessThanOrEqual(600);
    const normal = (await drawer.boundingBox())!.width;
    await drawer.getByRole("button", { name: "Expand drawer" }).click();
    const wide = (await drawer.boundingBox())!.width;
    expect(Math.abs(wide - (width < 768 ? width : Math.max(normal, width * 0.9)))).toBeLessThanOrEqual(2);
    await drawer.getByRole("button", { name: "Expand drawer" }).click();
    expect((await drawer.boundingBox())!.width).toBe(normal);
  }
  await drawer.getByLabel("Pool size (optional)", { exact: true }).fill("4");
  await drawer.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("dialog", { name: "Discard changes?" }).getByRole("button", { name: "Discard changes" }).click();
  await expect(drawer.getByRole("button", { name: "Edit", exact: true })).toBeVisible();
  expect(state.unexpected).toEqual([]);
});
