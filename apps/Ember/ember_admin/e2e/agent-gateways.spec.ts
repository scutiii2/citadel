import { expect, test } from "@playwright/test";
import { ADMIN_ACCOUNT, installFakeApi, newState } from "./fakeApi.ts";

interface AgentConfig {
  label: string;
  port: number;
  entry?: boolean;
  llm: { provider: string; gateway?: string; model?: string; fallback_gateways?: (string | { gateway: string; model?: string })[];
    max_turn_tokens?: number; max_turn_seconds?: number; max_tokens?: number; max_tool_rounds?: number };
}

test("ordered gateways fit each viewport and save only the edited agent", async ({ page }, testInfo) => {
  const state = newState();
  state.permissions = [...ADMIN_ACCOUNT.permissions, "agents.manage"];
  await installFakeApi(page, state);
  const agents: (AgentConfig & { id: string })[] = [
    { id: "ember", label: "Ember", port: 9100, entry: true, llm: { provider: "anthropic", gateway: "claude" } },
    { id: "researcher", label: "Researcher", port: 9104, llm: {
      provider: "anthropic", gateway: "claude", model: "claude-custom",
      fallback_gateways: [{ gateway: "openrouter", model: "router-custom" }, "bedrock"],
    } },
  ];
  const writes: { id: string; config: AgentConfig }[] = [];
  let refuse = false;
  await page.route("**/api/agents", (route) => route.fulfill({ json: agents.map((a) => ({ id: a.id, status: "running", tiers: [] })) }));
  await page.route("**/api/admin/agents", (route) => route.fulfill({ json: { agents } }));
  await page.route("**/api/admin/agents/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/gateways")) return route.fulfill({ json: { providers: { anthropic: [
      { id: "claude", label: "Claude", model: "claude-default", tiers: [] },
      { id: "openrouter", label: "OpenRouter", model: "router-default", tiers: [] },
      { id: "bedrock", label: "Bedrock", model: "bedrock-default", tiers: [] },
    ] } } });
    if (route.request().method() !== "PUT") throw new Error(`Unexpected gateway editor call: ${path}`);
    if (refuse) return route.fulfill({ status: 400, json: { detail: "This gateway is unavailable." } });
    const id = path.split("/").at(-1)!;
    const config = route.request().postDataJSON().config as AgentConfig;
    writes.push({ id, config });
    agents[agents.findIndex((a) => a.id === id)] = { id, ...config };
    return route.fulfill({ json: { id, ...config } });
  });
  await page.goto("/agents");
  await page.locator('[data-id="researcher"] [data-test="edit"]').click();
  const dialog = page.getByRole("dialog", { name: "Edit Researcher" });
  await expect(dialog.locator('[data-test="gateway-row"]')).toHaveCount(3);
  await dialog.getByRole("textbox", { name: "Total tokens per turn", exact: true }).fill("250000");
  await dialog.getByRole("textbox", { name: "Time per turn (seconds)", exact: true }).fill("600");
  await dialog.getByRole("textbox", { name: "Output tokens per model call", exact: true }).fill("8000");
  await dialog.getByRole("textbox", { name: "Model/tool rounds", exact: true }).fill("12");
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await expect(dialog.getByRole("combobox", { name: "Primary gateway", exact: true })).toBeVisible();
    await dialog.locator('[data-test="run-limits"]').scrollIntoViewIfNeeded();
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await expect(dialog.getByRole("textbox", { name: "Total tokens per turn", exact: true })).toHaveValue("250000");
    for (const theme of ["light", "dark"]) {
      await page.evaluate((value) => { document.documentElement.style.colorScheme = value; }, theme);
      await page.screenshot({ path: testInfo.outputPath(`run-limits-${width}-${theme}.png`) });
    }
  }
  await dialog.getByRole("button", { name: "Move openrouter up", exact: true }).click();
  await expect(dialog.locator('[data-test="gateway"]')).toHaveValue("openrouter");
  await expect(dialog.locator('[data-test="model"]')).toHaveValue("router-custom");
  await expect(dialog.locator('[data-test="unsaved"]')).toBeVisible();
  expect(writes).toEqual([]);
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.evaluate(() => { document.documentElement.style.colorScheme = "dark"; });
  await page.screenshot({ path: testInfo.outputPath("gateway-list-dark.png") });
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  expect(writes).toEqual([{ id: "researcher", config: expect.objectContaining({ llm: expect.objectContaining({
    gateway: "openrouter", model: "router-custom", fallback_gateways: [
      { gateway: "claude", model: "claude-custom" }, { gateway: "bedrock" },
    ], max_turn_tokens: 250000, max_turn_seconds: 600, max_tokens: 8000, max_tool_rounds: 12,
  }) }) }]);
  expect(agents[0]!.llm?.gateway).toBe("claude");
  await expect(page.locator('[data-id="researcher"]')).toContainText("openrouter → claude → bedrock");
  await page.locator('[data-id="researcher"] [data-test="edit"]').click();
  await expect(dialog.locator('[data-test="max-turn-tokens"]')).toHaveValue("250000");
  await expect(dialog.locator('[data-test="max-turn-seconds"]')).toHaveValue("600");
  await dialog.locator('[data-test="max-turn-tokens"]').fill("500000");
  const rows = dialog.locator('[data-test="gateway-row"]');
  await rows.nth(2).locator('[data-test="drag-handle"]').dragTo(rows.nth(0));
  await expect(dialog.locator('[data-test="gateway"]')).toHaveValue("bedrock");
  refuse = true;
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog.locator('[data-test="form-error"]')).toContainText("This gateway is unavailable.");
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('[data-test="max-turn-tokens"]')).toHaveValue("500000");
  expect(writes).toHaveLength(1);
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.locator('[data-id="researcher"]')).toContainText("openrouter → claude → bedrock");
  expect(state.unexpected).toEqual([]);
});
