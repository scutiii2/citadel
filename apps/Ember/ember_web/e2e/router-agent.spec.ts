import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { flipSwitch, logIn } from "./helpers.ts";

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

for (const width of [1440, 768, 767, 375, 320]) {
  test(`grouped Agents filters, descriptions and confirmed switches at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript(() => localStorage.clear());
    const api = await installFakeApi(page);
    await logIn(page);
    const base = { id: "ember", label: "Ember", entry: false, orchestrator: false, focus: "Keeps your conversation in context.", status: "running", provider: "Anthropic", gateway: "Direct", model: "claude-sonnet-4-6", tiers: [] };
    const agents = [
      { ...base, entry: true, orchestrator: true },
      { ...base, id: "router", label: "Router", internal_role: "router", focus: "Chooses a specialist and model.", provider: "Local", gateway: "Laya", model: "laya-english", decision: { fallback: true, fallback_available: false } },
      { ...base, id: "conductor", label: "Conductor", orchestrator: true, focus: "Coordinates several specialists." },
      { ...base, id: "forge", label: "Forge", focus: "Builds, debugs and reviews code.", provider: "OpenAI", model: "gpt-5.4", tiers: [{ tier: "Quick", id: "gpt-5.4-mini", use_for: "Small edits" }, { tier: "Standard", id: "gpt-5.4", use_for: "Implementation" }, { tier: "Deep", id: "gpt-5.4-pro", use_for: "Complex debugging" }] },
      { ...base, id: "scout", label: "Scout", status: "offline", focus: "Finds sources and connects evidence.", gateway: "OpenRouter" },
      { ...base, id: "quill", label: "Quill", status: "disabled", focus: "Shapes clear drafts and careful edits." },
      { ...base, id: "atlas", label: "Atlas", focus: "", provider: "Google", gateway: "OpenRouter", model: "gemini-2.5-pro" },
    ];
    await page.route("**/api/agents", route => route.fulfill({ json: agents }));
    await page.goto("/agents");
    await expect(page.locator(".agent-card")).toHaveCount(7);
    await expect(page.locator(".agent-group").first().locator(".agent-card")).toHaveCount(2);
    for (const theme of ["light", "dark"]) {
      await page.evaluate(theme => { document.documentElement.style.colorScheme = theme; }, theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      expect(await page.locator('.agents-view').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
      const targets = await page.locator('.filters button, .page-actions button, .agent-controls label').evaluateAll(els => els.map(el => ({ width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height })));
      expect(targets.every(target => target.width >= 44 && target.height >= 44)).toBe(true);
      if (width === 1440 || width === 375) {
        const height = await page.locator('.agents-view').evaluate(el => el.scrollHeight + 60);
        await page.setViewportSize({ width, height });
        await page.screenshot({ path: info.outputPath(`agents-A-${width}-${theme}.png`), fullPage: true });
        await page.setViewportSize({ width, height: 1000 });
      }
    }
    await page.getByRole('button', { name: 'Offline', exact: true }).click();
    await expect(page.locator('.agent-card')).toHaveCount(1);
    await page.getByRole('button', { name: 'All', exact: true }).click();
    await page.getByRole('searchbox', { name: 'Search agents' }).fill('gpt-5.4-pro');
    await expect(page.locator('.agent-card')).toHaveCount(1);
    await page.getByRole('button', { name: 'Open Forge', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Forge', exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await page.getByRole('searchbox', { name: 'Search agents' }).fill('');
    let answer!: () => void;
    const reply = new Promise<void>(resolve => { answer = resolve; });
    await page.route('**/api/account-agents/forge', async route => {
      await reply;
      await route.fulfill({ json: { disabled: ['forge'] } });
    });
    await flipSwitch(page, 'Use Forge');
    const toggle = page.getByRole('switch', { name: 'Use Forge', exact: true });
    await expect(toggle).toBeDisabled();
    await expect(toggle).toBeChecked();
    answer();
    await expect(toggle).not.toBeChecked();
    await expect(toggle).toBeEnabled();
    expect(api.unexpected).toEqual([]);
  });
}
