import { expect, test, type Page } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

const report = {
  total_cost: null, currency: "USD", unpriced_tokens: 0, days: 30, since: "2026-11-01", total_tokens: 0,
  input_tokens: 0, output_tokens: 0, summary_tokens: 0, turns: 0, chats: 0, by_agent: [], daily: [],
  hourly: Array(24).fill(0), group_by: "agent", groups: [],
};

/** A fake account with one 6-hour reset and a weekly boost; the two changes alter what it answers. */
async function account(page: Page) {
  await installFakeApi(page, newState());
  let used = 900_000;
  let auto = false;
  let resets = [{ id: "r_1", kind: "six_hour", granted_at: "2026-11-01T00:00:00", expires_at: "2099-02-01T00:00:00" }];
  const overview = () => ({
    six_hour: { used, limit: 1_000_000, reset_at: used ? "2026-11-27T20:00:00" : null, boost: null },
    weekly: { used: 3_100_000, limit: 7_500_000, reset_at: "2026-12-01T08:00:00", boost: { percent: 50, ends_at: "2099-01-01T00:00:00" } },
    resets, auto_use: auto, cached_token_weight: 0.1,
  });
  // Registered after the fake API, so these answer first.
  await page.route("**/api/usage?**", (route) => route.fulfill({ json: { ...overview(), report } }));
  await page.route("**/api/usage/resets/r_1/use", (route) => {
    used = 0;
    resets = [];
    return route.fulfill({ json: overview() });
  });
  await page.route("**/api/usage/auto-reset", (route) => {
    auto = (route.request().postDataJSON() as { enabled: boolean }).enabled;
    return route.fulfill({ json: overview() });
  });
}

test("a reset is used from the usage ring and the switch is saved", async ({ page }) => {
  await account(page);
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/chat");
  await page.locator(".app-header button.meter").click();
  const panel = page.locator(".usage-meter .panel");
  await expect(panel).toContainText("Weekly limit: +50% until");
  await expect(panel).toContainText("Cached input counts at 10%.");
  if (process.env.PROBE_RING) await page.screenshot({ path: process.env.PROBE_RING });

  await panel.getByRole("button", { name: "Use 6-hour reset" }).click();
  const ask = page.getByRole("dialog", { name: "Use 6-hour reset?" });
  await page.keyboard.press("Escape");
  await expect(ask).toBeHidden();
  await expect(panel).toBeVisible();

  await panel.getByRole("button", { name: "Use 6-hour reset" }).click();
  await ask.getByRole("button", { name: "Use reset" }).click();
  await expect(panel).toContainText("0 of 1,000,000 tokens");
  await expect(panel).toContainText("You have no free resets.");

  await panel.getByText("Use automatically").click();
  await expect(panel.getByRole("switch")).toBeChecked();
});

test("a phone has the resets on the Usage page", async ({ page }) => {
  await account(page);
  await page.setViewportSize({ width: 375, height: 740 });
  await page.goto("/usage");
  const section = page.getByRole("region", { name: "Free resets" });
  await section.getByRole("button", { name: "Use 6-hour reset" }).scrollIntoViewIfNeeded();
  expect(await page.evaluate<boolean>("document.documentElement.scrollWidth <= window.innerWidth")).toBe(true);
  if (process.env.PROBE_PHONE) await page.screenshot({ path: process.env.PROBE_PHONE });

  await section.getByRole("button", { name: "Use 6-hour reset" }).click();
  await page.getByRole("dialog", { name: "Use 6-hour reset?" }).getByRole("button", { name: "Use reset" }).click();
  await expect(section).toContainText("You have no free resets.");
});
