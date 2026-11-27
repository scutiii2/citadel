import { expect, test } from "@playwright/test";
import { ACCOUNT, installFakeApi, newState } from "./fakeApi.ts";

/** A 1x1 PNG, so the tile has a real picture to draw. */
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==", "base64");
const SUMMARY = {
  id: "c1", title: "Saved chat", agent_id: "ember", message_count: 4, running: false,
  created_at: "2026-11-27T10:00:00", updated_at: "2026-11-27T10:05:00",
};
const HEADER = "[File file_id: f_photo | image | 1 pages | expires_at: 4000000000 | preserve this file_id when delegating]";
const MESSAGES = [
  { role: "user", content: "first question" },
  { role: "assistant", content: "first answer" },
  { role: "user", content: `describe this\n\n[[ATTACHMENT filename="photo.png" chars="0" truncated="false"]]\n${HEADER}\n[[/ATTACHMENT]]` },
  { role: "assistant", content: "second answer" },
];

test("retry puts the last question and its picture back in the box, and cancel brings the exchange back", async ({ page }) => {
  await installFakeApi(page, newState());
  // Registered after the fake API, so these answer first.
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { ...ACCOUNT, permissions: [...ACCOUNT.permissions, "files.upload", "files.download"] } }));
  await page.route("**/api/chats", (route) => route.fulfill({ json: [SUMMARY] }));
  await page.route("**/api/chats/c1", (route) => route.fulfill({ json: { ...SUMMARY, messages: MESSAGES } }));
  await page.route("**/api/attachments/files/f_photo/content", (route) => route.fulfill({ contentType: "image/png", body: PNG }));
  await page.goto("/chat/c1");
  const chat = page.locator(".chat-view");
  await expect(chat.getByText("second answer")).toBeVisible();
  await expect(chat.getByRole("button", { name: "Edit and resend" })).toHaveCount(0);

  await chat.getByText("describe this").hover();
  await chat.locator(".main").getByRole("button", { name: "Retry" }).click();

  await expect(chat.locator(".composer textarea")).toHaveValue("describe this");
  await expect(chat.locator(".composer .image-tile img")).toBeVisible();
  await expect(chat.getByText("second answer")).toHaveCount(0);
  await expect(chat.getByText("first answer")).toBeVisible();
  if (process.env.PROBE_RETRY) await page.screenshot({ path: process.env.PROBE_RETRY });

  await chat.getByRole("button", { name: "Cancel" }).click();

  await expect(chat.getByText("second answer")).toBeVisible();
  await expect(chat.locator(".composer textarea")).toHaveValue("");
  await expect(chat.locator(".composer .image-tile")).toHaveCount(0);
});
