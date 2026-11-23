import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("the drawer expands, scrolls its own body, keeps the footer reachable and discards after asking", async ({ page }) => {
  const state = newState();
  await installFakeApi(page, state);
  await page.goto("/tool-services");
  const opener = page.getByRole("button", { name: "Open Bard", exact: true });
  await opener.click();
  const drawer = page.getByRole("dialog", { name: "Bard", exact: true });
  const enabled = drawer.getByRole("switch", { name: "Enabled" });
  await drawer.locator("label.toggle").click();
  await expect(enabled).not.toBeChecked();
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
    await drawer.getByRole("button", { name: "Restore drawer size" }).click();
    expect((await drawer.boundingBox())!.width).toBe(normal);
  }
  await drawer.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("dialog", { name: "Discard changes?" }).getByRole("button", { name: "Discard changes" }).click();
  await expect(enabled).toBeChecked();
  expect(state.unexpected).toEqual([]);
});
