import { expect, test } from "@playwright/test";
import { ACCOUNT, ANSWER, installFakeApi, PASSWORD } from "./fakeApi.ts";

test("second brain toggle persists per chat and is sent with the next question", async ({ page }) => {
  const api = await installFakeApi(page, { admin: true });
  api.capabilities.set("obsidian", { name: "obsidian", enabled: true, label: "Obsidian", tools: ["tool_obsidian_write"], resources: [] });
  api.accountCapabilities.capabilities.add("obsidian");
  api.chats.set("second-brain-0001", { id: "second-brain-0001", title: "Second brain", agent_id: "agent-1", messages: [], running: false });
  await page.goto("/");
  await page.getByLabel("Username").fill(ACCOUNT.username);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await page.goto("/chat/second-brain-0001");
  await page.getByRole("button", { name: "Chat settings" }).click();
  const label = page.locator("label.toggle").filter({ hasText: "Save to second brain" });
  await expect(label.getByRole("switch")).not.toBeChecked();
  await label.click();
  await expect(label.getByRole("switch")).toBeChecked();
  await page.reload();
  await page.getByRole("button", { name: "Chat settings" }).click();
  await expect(label.getByRole("switch")).toBeChecked();
  await page.getByRole("button", { name: "Chat settings" }).click();
  const input = page.getByPlaceholder(/Ask something/);
  await input.fill("Remember our decision");
  await input.press("Enter");
  await expect(page.getByText(ANSWER)).toBeVisible();
  expect(api.turns[0]).toMatchObject({ save_to_second_brain: true });
  expect(api.unexpected).toEqual([]);
});
