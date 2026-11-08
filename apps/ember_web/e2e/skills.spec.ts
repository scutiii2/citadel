import { expect, test } from "@playwright/test";
import { installFakeApi, type StoredSkill } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

// Chrome's headless default hides scrollbars, including in screenshots.
test.use({ launchOptions: { ignoreDefaultArgs: ["--hide-scrollbars"] } });

const skill = (id: number, status: StoredSkill["status"], extra: Partial<StoredSkill> = {}): StoredSkill => ({
  id, title: `Skill ${id}`, when_to_use: "When an app needs restarting", steps: "Stop the app.\nStart it again.",
  tools: "tool_srv_stopApp", status, successes: 3, failures: 1, failing: false, created_at: "2026-10-25T00:00:00Z", ...extra,
});

test("skills workspace keeps drafts, pane scrollbars and Save reachable in both themes and responsive modes", async ({ page }, info) => {
  const api = await installFakeApi(page);
  const longTitle = "A long skill title that must wrap without clipping while the editor stays usable";
  api.skills.set(1, skill(1, "proposed", { title: longTitle }));
  for (let id = 2; id <= 14; id++) api.skills.set(id, skill(id, id % 2 ? "active" : "proposed"));
  await logIn(page);
  await page.goto("/skills");
  const selectedRow = page.getByRole("button", { name: `Edit skill ${longTitle}`, exact: true });
  await selectedRow.focus();
  await selectedRow.press("Enter");
  const editor = page.getByRole("form", { name: "Skill editor", exact: true });
  await expect(editor.getByLabel("Title", { exact: true })).toBeFocused();
  await editor.getByLabel("Steps", { exact: true }).fill("Keep this draft across viewport changes.");
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [1440, 768, 767, 375]) {
      await page.setViewportSize({ width, height: 812 });
      await expect(editor).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(await editor.evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true);
      await expect(editor.getByLabel("Steps", { exact: true })).toHaveValue("Keep this draft across viewport changes.");
      await expect(page.getByRole("complementary", { name: "Skill list" })).toBeVisible({ visible: width >= 768 });
      const title = editor.getByLabel("Title", { exact: true });
      await expect.poll(() => title.evaluate(e => e.scrollHeight <= e.clientHeight + 1)).toBe(true);
      const save = editor.getByRole("button", { name: "Save", exact: true });
      await expect(save).toBeInViewport();
      const box = await save.boundingBox();
      expect(box!.y + box!.height).toBeLessThanOrEqual(812 - (width < 768 ? 52 : 0));
      expect(await editor.locator(".editor-scroll").evaluate(e => getComputedStyle(e).overflowY)).toBe("scroll");
      if (width >= 768) {
        const selected = page.locator(".list-row-frame.active");
        const approveBox = await selected.getByRole("button", { name: "Approve", exact: true }).boundingBox();
        const rowBox = await selected.boundingBox();
        expect(approveBox!.y + approveBox!.height).toBeLessThanOrEqual(rowBox!.y + rowBox!.height);
        expect(await page.locator(".skills .list-scroll").evaluate(e => getComputedStyle(e).overflowY)).toBe("scroll");
      }
      await page.screenshot({ path: info.outputPath(`skills-${colorScheme}-${width}.png`) });
    }
  }
  await editor.getByRole("button", { name: "‹ All skills", exact: true }).click();
  const discard = page.getByRole("dialog", { name: "Discard your changes?" });
  await discard.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(editor.getByLabel("Steps", { exact: true })).toHaveValue("Keep this draft across viewport changes.");
  await editor.getByText("Manage skill", { exact: false }).click();
  const deletion = editor.getByRole("button", { name: `Delete skill ${longTitle}`, exact: true });
  await expect(deletion).toBeVisible();
  const deleteBox = await deletion.boundingBox();
  expect(deleteBox!.height).toBeGreaterThanOrEqual(44);
  await deletion.click();
  const confirmation = page.getByRole("dialog", { name: "Delete this skill?" });
  await confirmation.getByRole("button", { name: "Cancel", exact: true }).click();
  await editor.getByRole("button", { name: "Save", exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(selectedRow).toBeFocused();
  expect(api.skills.get(1)?.steps).toBe("Keep this draft across viewport changes.");
  expect(api.unexpected).toEqual([]);
});

test("skills approve, search, retire, send back and delete use the existing API contracts", async ({ page }) => {
  const api = await installFakeApi(page);
  api.skills.set(1, skill(1, "proposed"));
  await logIn(page);
  await page.goto("/skills");
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText("Skill approved.", { exact: true })).toBeVisible();
  expect(api.skills.get(1)?.status).toBe("active");
  await expect(page.getByRole("form", { name: "Skill editor" })).toHaveCount(0);
  await page.getByRole("searchbox", { name: "Search skills" }).fill("nothing matches");
  await expect(page.getByText("No skills match your search.")).toBeVisible();
  await page.getByRole("searchbox", { name: "Search skills" }).fill("restarting");
  await page.getByRole("button", { name: "Edit skill Skill 1", exact: true }).click();
  const editor = page.getByRole("form", { name: "Skill editor", exact: true });
  await editor.getByText("Manage skill", { exact: false }).click();
  await editor.getByRole("button", { name: "Retire", exact: true }).click();
  await expect(page.getByText("Skill retired.", { exact: true })).toBeVisible();
  await editor.getByRole("button", { name: "Send back for review", exact: true }).click();
  await expect(page.getByText("Skill sent back for review.", { exact: true })).toBeVisible();
  await editor.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.getByText("Skill rejected.", { exact: true })).toBeVisible();
  await editor.getByRole("button", { name: "Delete skill Skill 1", exact: true }).click();
  await page.getByRole("dialog", { name: "Delete this skill?" }).getByRole("button", { name: "Delete skill", exact: true }).click();
  await expect(page.getByText("No skills yet.")).toBeVisible();
  expect(api.skills.size).toBe(0);
  expect(api.unexpected).toEqual([]);
});
