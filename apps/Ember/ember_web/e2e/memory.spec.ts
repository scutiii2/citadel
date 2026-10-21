import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test("memory workspace preserves drafts and keeps Save reachable across desktop, tablet and mobile", async ({ page }, info) => {
  const api = await installFakeApi(page);
  api.memories.set(1, { id: 1, text: "Prefers clear recommendations. " + "x".repeat(450), created_at: "2026-10-18T00:00:00Z" });
  await logIn(page);
  await page.goto("/memory");
  await page.getByRole("button", { name: "Edit memory 1", exact: true }).click();
  const editor = page.getByRole("form", { name: "Memory editor", exact: true });
  await editor.getByLabel("Memory", { exact: true }).fill("A corrected preference");
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [1440, 768, 375]) {
      await page.setViewportSize({ width, height: 812 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expect(page.getByRole("button", { name: "Delete memory 1", exact: true })).toBeHidden();
      await expect(editor).toBeVisible();
      expect(await editor.evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true);
      await expect(editor.getByRole("button", { name: "Save", exact: true })).toBeInViewport();
      const box = await editor.getByRole("button", { name: "Save", exact: true }).boundingBox();
      expect(box!.y + box!.height).toBeLessThanOrEqual(812 - (width < 768 ? 52 : 0));
      await expect(editor.getByLabel("Memory", { exact: true })).toHaveValue("A corrected preference");
      await expect(page.getByRole("complementary", { name: "Memory list" })).toBeVisible({ visible: width >= 768 });
      await page.screenshot({ path: info.outputPath(`memory-${colorScheme}-${width}.png`) });
    }
  }
  await editor.getByRole("button", { name: "‹ All memories", exact: true }).click();
  const discard = page.getByRole("dialog", { name: "Discard your changes?" });
  await discard.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(editor.getByLabel("Memory", { exact: true })).toHaveValue("A corrected preference");
  await editor.locator('.manage-memory > summary').click();
  await editor.getByRole("button", { name: "Delete memory 1", exact: true }).click();
  const confirmation = page.getByRole("dialog", { name: "Delete this memory?" });
  await confirmation.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(editor.getByLabel("Memory", { exact: true })).toHaveValue("A corrected preference");
  await editor.getByRole("button", { name: "Save", exact: true }).click();
  await expect(editor.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  await expect(editor).toBeVisible();
  expect(api.memories.get(1)?.text).toBe("A corrected preference");
  await editor.getByRole("button", { name: "‹ All memories", exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Edit memory 1", exact: true })).toBeVisible();
  expect(api.unexpected).toEqual([]);
});

test("memory is separate from notes: create, search, edit and confirm deletion", async ({ page }) => {
  const api = await installFakeApi(page);
  await logIn(page);
  await page.goto("/memory");
  await expect(page.getByText("No saved memories yet.")).toBeVisible();
  await page.getByRole("button", { name: "Add memory", exact: true }).click();
  const editor = page.getByRole("form", { name: "Memory editor", exact: true });
  await editor.getByLabel("Memory", { exact: true }).fill("Prefers concise answers");
  await editor.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("article")).toContainText("Prefers concise answers");
  await page.getByRole("searchbox").fill("coffee");
  await expect(page.getByText("No memories match your search.")).toBeVisible();
  await expect(editor.getByLabel("Memory", { exact: true })).toHaveValue("Prefers concise answers");
  await page.getByRole("searchbox").fill("");
  await page.getByRole("button", { name: "Edit memory 1", exact: true }).click();
  const edit = page.getByRole("form", { name: "Memory editor", exact: true });
  await edit.getByLabel("Memory", { exact: true }).fill("Prefers detailed answers");
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("article")).toContainText("Prefers detailed answers");
  await page.getByRole("button", { name: "Edit memory 1", exact: true }).click();
  await edit.locator('.manage-memory > summary').click();
  await page.getByRole("button", { name: "Delete memory 1", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "Delete this memory?" });
  await confirm.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(api.memories.size).toBe(1);
  await page.getByRole("button", { name: "Delete memory 1", exact: true }).click();
  await confirm.getByRole("button", { name: "Delete memory", exact: true }).click();
  await expect(page.getByText("No saved memories yet.")).toBeVisible();
  expect(api.memories.size).toBe(0);
  expect(api.notes.size).toBe(0);
  expect(api.unexpected).toEqual([]);
});
