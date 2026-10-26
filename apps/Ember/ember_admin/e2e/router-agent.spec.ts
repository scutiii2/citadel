import { expect, test } from "@playwright/test";
import { ADMIN_ACCOUNT, installFakeApi, newState } from "./fakeApi.ts";

test("Router settings save explicitly, retain failed drafts and fit narrow screens", async ({ page }) => {
  const state = newState();
  state.permissions = [...ADMIN_ACCOUNT.permissions, "agents.manage"];
  await installFakeApi(page, state);
  let router: Record<string, unknown> = { id: "router", label: "Router", port: 9117,
    role: "router", enabled: true, entry: false, delegable: false,
    plan_tool: false, tools: { deny: ["*"] }, llm: { provider: "laya", gateway: "local" }, decision: {} };
  let refuse = false;
  const writes: Record<string, unknown>[] = [];
  await page.route("**/api/agents", route => route.fulfill({ json: [{ id: "router", status: router.enabled ? "running" : "disabled", tiers: [] }] }));
  await page.route("**/api/admin/agents", route => route.fulfill({ json: { agents: [router] } }));
  await page.route("**/api/admin/agents/**", route => {
    if (new URL(route.request().url()).pathname.endsWith("/gateways"))
      return route.fulfill({ json: { providers: { laya: [{ id: "local", label: "Local", model: "convaiinnovations/laya", tiers: [] }] } } });
    if (route.request().method() !== "PUT") throw new Error("Unexpected Router request");
    if (refuse) return route.fulfill({ status: 400, json: { detail: "Router settings could not be saved" } });
    const config = route.request().postDataJSON().config;
    writes.push(config);
    router = { id: "router", ...config };
    return route.fulfill({ json: router });
  });
  await page.goto("/agents");
  await expect(page.locator('[data-id="router"]')).toContainText("Internal / Router");
  await page.getByRole("button", { name: "Edit Router", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Edit Router" });
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await dialog.evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true);
  }
  for (const theme of ["light", "dark"]) {
    await page.evaluate(t => { document.documentElement.style.colorScheme = t; }, theme);
    await expect(dialog.locator('[data-test="routing-deadline"]')).toBeVisible();
  }
  await dialog.locator('[data-test="routing-deadline"]').fill("8");
  expect(writes).toHaveLength(0);
  refuse = true;
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog.locator('[data-test="form-error"]')).toContainText("could not be saved");
  await expect(dialog.locator('[data-test="routing-deadline"]')).toHaveValue("8");
  refuse = false;
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(writes[0]).toMatchObject({ role: "router", decision: { deadline_seconds: 8 },
    tools: { deny: ["*"] }, delegable: false });
  expect(state.unexpected).toEqual([]);
});
