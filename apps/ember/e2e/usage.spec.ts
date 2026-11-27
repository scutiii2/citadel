import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

const report = {
  total_cost: null, currency: "USD", unpriced_tokens: 0, days: 1, since: "2026-11-27", total_tokens: 0,
  input_tokens: 0, output_tokens: 0, summary_tokens: 0, turns: 0, chats: 0, by_agent: [], daily: [],
  hourly: Array(24).fill(0), group_by: "agent", groups: [],
};

test("the header's usage ring sits beside the account button and opens the numbers", async ({ page }) => {
  await installFakeApi(page, newState());
  // Registered after the fake API, so this answers first.
  await page.route("**/api/usage?**", (route) => route.fulfill({ json: {
    six_hour: { used: 250_000, limit: 1_000_000, reset_at: "2026-11-27T20:00:00" },
    weekly: { used: 3_100_000, limit: 5_000_000, reset_at: "2026-12-01T08:00:00" },
    report,
  } }));
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/chat");

  const ring = page.locator(".app-header button.meter");
  await expect(ring).toHaveAttribute("aria-label", "Usage limits: last 6 hours 25%, last 7 days 62%");
  const [ringBox, accountBox] = [await ring.boundingBox(), await page.locator(".app-header button.account").boundingBox()];
  expect(ringBox!.x + ringBox!.width).toBeLessThanOrEqual(accountBox!.x);
  expect(accountBox!.x - ringBox!.x - ringBox!.width).toBeLessThanOrEqual(8);

  await ring.click();
  const panel = page.locator(".usage-meter .panel");
  await expect(panel).toContainText("250,000 of 1,000,000 tokens");
  const box = (await panel.boundingBox())!;
  expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  if (process.env.PROBE_USAGE) await page.screenshot({ path: process.env.PROBE_USAGE });

  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
});
