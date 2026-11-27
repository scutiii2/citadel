import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

for (const width of [1280, 375]) {
  test(`a settings manager sends resets, resets everyone and removes a reset at ${width}px`, async ({ page }) => {
    const state = newState();
    await installFakeApi(page, state);
    await page.setViewportSize({ width, height: 700 });
    await page.goto("/usage");
    const fits = () => page.evaluate<boolean>("document.documentElement.scrollWidth <= window.innerWidth");

    await page.getByRole("button", { name: "Send resets", exact: true }).click();
    const send = page.getByRole("dialog", { name: "Send resets", exact: true });
    await send.locator("label.toggle", { hasText: "root" }).click();
    expect(await fits()).toBe(true);
    await send.getByRole("button", { name: "Send resets", exact: true }).click();
    await expect(page.getByText("Resets sent to 1 account.")).toBeVisible();

    await page.getByRole("button", { name: "Reset usage", exact: true }).click();
    const reset = page.getByRole("dialog", { name: "Reset usage", exact: true });
    await reset.getByRole("button", { name: "All users", exact: true }).click();
    await reset.getByRole("button", { name: "Reset usage", exact: true }).click();
    const ask = page.getByRole("dialog", { name: "Reset usage?" });
    await expect(ask).toContainText("all 1 enabled account");
    await ask.getByRole("button", { name: "Reset usage" }).click();
    await expect(page.getByText("Usage reset for 1 account.")).toBeVisible();

    await page.getByRole("button", { name: "View usage for root" }).click();
    await page.getByRole("button", { name: "Remove 6-hour and weekly reset 1" }).click();
    await page.getByRole("dialog", { name: "Remove reset?" }).getByRole("button", { name: "Remove", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Remove reset?" })).toBeHidden();
    await expect(page.getByRole("dialog", { name: "Usage for root" })).toBeVisible();
    expect(await fits()).toBe(true);

    expect(state.sent.map((entry) => entry.call)).toEqual([
      "POST /api/admin/usage-allowances/resets",
      "POST /api/admin/usage-allowances/clear",
      "DELETE /api/admin/usage-allowances/1/resets/r_1",
    ]);
    expect(state.sent[1]!.body).toEqual({ all: true, windows: ["six_hour"] });
    expect(state.unexpected).toEqual([]);
  });
}
