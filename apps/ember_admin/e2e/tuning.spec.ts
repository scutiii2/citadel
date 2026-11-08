import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";

test("Tuning saves and resets changes, and protects an unsaved draft", async ({ page }) => {
  const state = newState();
  state.permissions = ["tuning.manage", "capabilities.manage"];
  await installFakeApi(page, state);
  const defaults = { token_limits: { default: { max_output_tokens: 2048, max_context_tokens: 100000, max_tool_rounds: 15 } }, gateway_failover: {}, classifier: {} };
  let overrides: Record<string, number | boolean> = {};
  const changes: Record<string, number | boolean | null>[] = [];
  await page.route("**/api/admin/tuning", async route => {
    if (route.request().method() === "PUT") {
      const patch = route.request().postDataJSON().changes;
      changes.push(patch);
      for (const [key, value] of Object.entries(patch)) {
        if (value === null) delete overrides[key];
        else overrides[key] = value as number | boolean;
      }
    }
    const effective = structuredClone(defaults);
    effective.token_limits.default.max_tool_rounds = overrides["token_limits.default.max_tool_rounds"] as number ?? 15;
    await route.fulfill({ json: { defaults, overrides, effective } });
  });
  await page.goto("/admin/tuning");
  const rounds = page.getByRole("spinbutton", { name: "Max tool rounds", exact: true });
  await expect(rounds).toHaveValue("15");
  for (const colorScheme of ["light", "dark"]) {
    await page.evaluate(scheme => { document.documentElement.style.colorScheme = scheme; }, colorScheme);
    for (const width of [1280, 768, 375]) {
      await page.setViewportSize({ width, height: 800 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
  }
  await rounds.fill("3");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  expect(changes.at(-1)).toEqual({ "token_limits.default.max_tool_rounds": 3 });
  await page.reload();
  await expect(rounds).toHaveValue("3");
  await page.getByRole("button", { name: "Reset Max tool rounds", exact: true }).click();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(rounds).toHaveValue("15");
  expect(changes.at(-1)).toEqual({ "token_limits.default.max_tool_rounds": null });
  await rounds.fill("4");
  await page.getByRole("link", { name: "Capabilities", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Discard unsaved tuning?" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).last().click();
  await expect(rounds).toHaveValue("4");
  await page.getByRole("link", { name: "Capabilities", exact: true }).click();
  await page.getByRole("button", { name: "Discard changes", exact: true }).click();
  await expect(page).toHaveURL(/\/capabilities$/);
  expect(state.unexpected).toEqual([]);
});
