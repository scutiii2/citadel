import { expect, test } from "@playwright/test";
import { installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test.use({ launchOptions: { ignoreDefaultArgs: ["--hide-scrollbars"] } });

test("Notes searches title, full text and tags without replacing the current draft", async ({ page }, info) => {
  const api = await installFakeApi(page);
  const created = "2026-10-29T00:00:00";
  const first = "a".repeat(32), second = "b".repeat(32);
  api.notes.set(first, { id: first, title: "Ember interface ideas", body: "Workspace layout\n\nKeep search beside the list, leave room to write, and save only when ready.\n\n".repeat(6), tags: ["ember", "design"], agent_readable: false, last_editor: "user", created_at: created, updated_at: created });
  api.notes.set(second, { id: second, title: "Weekly review", body: "Plan the week. " + "Long content. ".repeat(30) + "Deeply indexed phrase", tags: ["planning"], agent_readable: false, last_editor: "user", created_at: created, updated_at: created });
  await logIn(page);
  await page.goto("/notes");
  const sidebar = page.getByRole("complementary", { name: "Notes list", exact: true });
  const search = sidebar.getByRole("searchbox", { name: "Search notes", exact: true });
  const list = page.getByRole("list", { name: "Notes", exact: true });
  await list.getByRole("button", { name: /Ember interface ideas/ }).focus();
  await list.getByRole("button", { name: /Ember interface ideas/ }).press("Enter");
  const editor = page.getByRole("form", { name: "Note editor", exact: true });
  await expect(editor.getByLabel("Title", { exact: true })).toBeFocused();
  await editor.getByLabel("Note text").fill("Unsaved working draft\n\nKeep this text when searching other notes.");
  await search.fill("PLANNING deeply");
  await expect(list.getByRole("button")).toHaveCount(1);
  await expect(list).toContainText("Weekly review");
  await expect(editor.getByLabel("Title", { exact: true })).toHaveValue("Ember interface ideas");
  await expect(editor.getByLabel("Note text")).toHaveValue("Unsaved working draft\n\nKeep this text when searching other notes.");
  await list.getByRole("button").click();
  await page.getByRole("dialog", { name: "Discard your changes?" }).getByRole("button", { name: "Cancel", exact: true }).click();
  await search.fill("nothing matches");
  await expect(page.getByText("No notes match your search.")).toBeVisible();
  await expect(editor.getByRole("button", { name: "Save", exact: true })).toBeEnabled();
  await sidebar.getByRole("button", { name: "Clear search", exact: true }).click();
  await expect(list.getByRole("button")).toHaveCount(2);
  await search.fill("Ember");
  await expect(list.getByRole("button")).toHaveCount(1);
  await search.fill("");
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [1440, 768, 767, 375]) {
      await page.setViewportSize({ width, height: 812 });
      await expect(editor.getByRole("button", { name: "Save", exact: true })).toBeInViewport();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect.poll(() => editor.getByLabel("Note text").evaluate(e => e.scrollHeight <= e.clientHeight + 1)).toBe(true);
      if (width >= 768) {
        await expect(search).toBeVisible();
        expect(await sidebar.locator(".list-scroll").evaluate(e => getComputedStyle(e).overflowY)).toBe("scroll");
      }
      await page.screenshot({ path: info.outputPath("notes-search-" + colorScheme + "-" + width + ".png") });
    }
  }
  await page.getByRole("button", { name: "All notes" }).click();
  await page.getByRole("dialog", { name: "Discard your changes?" }).getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(editor.getByLabel("Note text")).toHaveValue("Unsaved working draft\n\nKeep this text when searching other notes.");
  await editor.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved." })).toBeVisible();
  expect(api.notes.get(first)?.body).toBe("Unsaved working draft\n\nKeep this text when searching other notes.");
  await page.getByRole("button", { name: "All notes" }).click();
  await expect(list.getByRole("button", { name: /Ember interface ideas/ })).toBeFocused();
  await search.fill("no matching notes");
  const clearSearch = sidebar.getByRole("button", { name: "Clear search", exact: true });
  const clearBox = await clearSearch.boundingBox();
  expect(clearBox!.height).toBeGreaterThanOrEqual(44);
  await clearSearch.click();
  await search.fill("planning");
  const newNote = page.getByRole("button", { name: "New note", exact: true });
  const newBox = await newNote.boundingBox();
  expect(newBox!.height).toBeGreaterThanOrEqual(44);
  await newNote.click();
  await editor.getByLabel("Title", { exact: true }).fill("A new draft outside the filter");
  await page.getByRole("button", { name: "All notes" }).click();
  await page.getByRole("dialog", { name: "Discard your changes?" }).getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(editor.getByLabel("Title", { exact: true })).toHaveValue("A new draft outside the filter");
  expect(api.unexpected).toEqual([]);
});
