import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test("Agents shows internal Router in running, offline and disabled states", async ({ page }) => {
  const api = await installFakeApi(page);
  await logIn(page);
  let status = "running";
  await page.route("**/api/agents", route => route.fulfill({ json: [{ id: "router", label: "Router",
    entry: false, orchestrator: false, focus: "Chooses an agent and model", status,
    provider: "laya", gateway: "local", model: "convaiinnovations/laya", tiers: [],
    internal_role: "router", decision: { english: true, typed: true, fallback: true } }] }));
  await page.goto("/agents");
  const card = page.locator(".agent-card");
  await expect(card).toContainText("Internal / Router");
  await expect(card).toContainText("Jev fallback");
  await expect(card).toContainText("Running");
  for (const next of ["offline", "disabled"]) {
    status = next;
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await expect(card).toHaveClass(new RegExp(next));
  }
  expect(await card.getByRole("button").count()).toBe(1);
  expect(api.unexpected).toEqual([]);
});
