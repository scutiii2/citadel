import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test("memory list and editor fit desktop, tablet and mobile in both themes", async ({ page }) => {
  const api = await installFakeApi(page);
  api.memories.set(1, { id: 1, text: "Prefers clear recommendations. " + "x".repeat(450), created_at: "2026-10-18T00:00:00Z" });
  await logIn(page);
  await page.goto("/memory");
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [1440, 768, 375]) {
      await page.setViewportSize({ width, height: 812 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expect(page.getByRole("button", { name: "Delete memory 1", exact: true })).toBeHidden();
      await page.getByRole("button", { name: "Edit memory 1", exact: true }).click();
      const editor = page.getByRole("dialog", { name: "Edit memory", exact: true });
      await expect(editor).toBeVisible();
      expect(await editor.evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true);
      if (width < 768) {
        const box = await editor.boundingBox();
        const bottom = await page.locator(".memory-editor").evaluate(e => parseFloat(getComputedStyle(e).bottom));
        expect(box!.y + box!.height).toBeLessThanOrEqual(812 - bottom + 1);
        expect(box!.width).toBe(375);
      }
      await editor.getByRole("button", { name: "Cancel", exact: true }).click();
      await expect(editor).toBeHidden();
    }
  }
  await page.getByRole("button", { name: "Edit memory 1", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "Edit memory", exact: true });
  await editor.getByLabel("Memory", { exact: true }).fill("A corrected preference");
  await editor.getByRole("button", { name: "Delete memory 1", exact: true }).click();
  const confirmation = page.getByRole("dialog", { name: "Delete this memory?" });
  await confirmation.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(editor.getByLabel("Memory", { exact: true })).toHaveValue("A corrected preference");
  await editor.getByRole("button", { name: "Save", exact: true }).click();
  await expect(editor).toBeHidden();
  expect(api.memories.get(1)?.text).toBe("A corrected preference");
  expect(api.unexpected).toEqual([]);
});

test("memory is separate from notes: create, search, edit and confirm deletion", async ({ page }) => {
  const api = await installFakeApi(page);
  await logIn(page);
  await page.goto("/memory");
  await expect(page.getByText("No saved memories yet.")).toBeVisible();
  await page.getByRole("button", { name: "Add memory", exact: true }).click();
  const editor = page.getByRole("dialog", { name: "Add memory", exact: true });
  await editor.getByLabel("Memory", { exact: true }).fill("Prefers concise answers");
  await editor.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("article")).toContainText("Prefers concise answers");
  await page.getByRole("searchbox").fill("coffee");
  await expect(page.getByText("No memories match your search.")).toBeVisible();
  await page.getByRole("searchbox").fill("");
  await page.getByRole("button", { name: "Edit memory 1", exact: true }).click();
  const edit = page.getByRole("dialog", { name: "Edit memory", exact: true });
  await edit.getByLabel("Memory", { exact: true }).fill("Prefers detailed answers");
  await edit.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("article")).toContainText("Prefers detailed answers");
  await page.getByRole("button", { name: "Edit memory 1", exact: true }).click();
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
