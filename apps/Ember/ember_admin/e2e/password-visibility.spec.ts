import { expect, test } from "@playwright/test";
import { installFakeApi, newState } from "./fakeApi.ts";
import { installFakeApi as installLoginApi, PASSWORD } from "./workspaceFakeApi.ts";

test("admin login can show and hide the password without submitting", async ({ page }) => {
  await installLoginApi(page);
  await page.goto("/login");
  const password = page.getByLabel("Password", { exact: true });
  await password.fill(PASSWORD);
  await page.getByRole("button", { name: "Show password", exact: true }).click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(password).toHaveValue(PASSWORD);
  await page.getByRole("button", { name: "Hide password", exact: true }).press("Enter");
  await expect(password).toHaveAttribute("type", "password");
  await expect(password).toHaveValue(PASSWORD);
  await expect(page).toHaveURL(/\/login/);
});

test("profile password visibility is independent for each field", async ({ page }) => {
  await installFakeApi(page, newState());
  await page.goto("/profile");
  await page.getByRole("button", { name: "Change password", exact: true }).click();
  const next = page.getByLabel("New password", { exact: true });
  const repeat = page.getByLabel("Repeat new password", { exact: true });
  await next.fill("new-password");
  await repeat.fill("new-password");
  await page.getByRole("button", { name: "Show password", exact: true }).first().click();
  await expect(next).toHaveAttribute("type", "text");
  await expect(next).toHaveValue("new-password");
  await expect(repeat).toHaveAttribute("type", "password");
  await expect(page.getByLabel("Current password", { exact: true })).toHaveAttribute("type", "password");
});
