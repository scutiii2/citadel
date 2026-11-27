import { expect, test } from "@playwright/test";
import { ACCOUNT, installFakeApi, newState } from "./fakeApi.ts";

test("a file dropped anywhere on the chat is attached, and one dropped elsewhere never replaces the app", async ({ page }) => {
  await installFakeApi(page, newState());
  // Registered after the fake API, so these answer first.
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { ...ACCOUNT, permissions: [...ACCOUNT.permissions, "files.upload"] } }));
  let uploads = 0;
  await page.route("**/api/attachments/file", (route) => {
    uploads++;
    return route.fulfill({ json: {
      filename: "notes.txt", file_id: "f_1", kind: "text", pages: null, expires_at: null, text: "hello",
      char_count: 5, truncated: false, table: null, read: null,
    } });
  });
  await page.goto("/chat");
  await expect(page.locator(".chat-view .composer")).toBeVisible();

  /** Fires a file drag on the element and says whether the page claimed it. */
  const drag = (selector: string, type: "dragover" | "drop") => page.evaluate(([selector, type]) => {
    const doc = (globalThis as any).document;
    const data = new (globalThis as any).DataTransfer();
    data.items.add(new (globalThis as any).File(["hello"], "notes.txt", { type: "text/plain" }));
    const event = new (globalThis as any).DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: data });
    doc.querySelector(selector).dispatchEvent(event);
    return event.defaultPrevented as boolean;
  }, [selector, type] as const);

  // Above the composer, on the messages.
  expect(await drag(".chat-view .scroller", "dragover")).toBe(true);
  await expect(page.locator(".chat-view .main")).toHaveClass(/file-drag/);
  if (process.env.PROBE_DROP) await page.screenshot({ path: process.env.PROBE_DROP });
  expect(await drag(".chat-view .scroller", "drop")).toBe(true);
  await expect(page.locator(".chat-view .attachments li")).toContainText("notes.txt");
  await expect(page.locator(".chat-view .main")).not.toHaveClass(/file-drag/);
  expect(uploads).toBe(1);

  // On the composer: attached once, not once per drop zone it passes through.
  await drag(".chat-view .composer", "drop");
  await expect(page.locator(".chat-view .attachments li")).toHaveCount(2);
  expect(uploads).toBe(2);

  // Outside the chat.
  expect(await drag("body", "drop")).toBe(true);
  expect(uploads).toBe(2);
});
