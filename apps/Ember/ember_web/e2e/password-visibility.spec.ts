import { expect, test } from "@playwright/test";
import { ACCOUNT, PASSWORD, installFakeApi } from "./fakeApi.ts";
import { logIn } from "./helpers.ts";

test("login password can be shown and hidden without changing it or submitting", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await installFakeApi(page);
  await page.goto("/login");
  await page.getByLabel("Username", { exact: true }).fill(ACCOUNT.username);
  const password = page.getByLabel("Password", { exact: true });
  await password.fill(PASSWORD);
  await expect(password).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Show password", exact: true }).click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(password).toHaveValue(PASSWORD);
  await expect(page).toHaveURL(/\/login/);
  await page.getByRole("button", { name: "Hide password", exact: true }).press("Enter");
  await expect(password).toHaveAttribute("type", "password");
  await expect(password).toHaveValue(PASSWORD);
  await expect(page).toHaveURL(/\/login/);
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page.getByPlaceholder(/Ask something/)).toBeVisible();
});

test("registration offers password visibility", async ({ page }) => {
  await installFakeApi(page);
  await page.goto("/register");
  const password = page.getByLabel("Password", { exact: true });
  await password.fill("new-password");
  await page.getByRole("button", { name: "Show password", exact: true }).click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(password).toHaveValue("new-password");
  await expect(password).toHaveAttribute("autocomplete", "new-password");
});

test("account password controls reveal each field independently", async ({ page }) => {
  await installFakeApi(page);
  await logIn(page);
  await page.goto("/account");
  await page.getByRole("button", { name: "Change password", exact: true }).click();
  const next = page.getByLabel("New password", { exact: true });
  const repeat = page.getByLabel("Repeat new password", { exact: true });
  const current = page.getByLabel("Current password", { exact: true });
  await next.fill("new-password");
  await repeat.fill("new-password");
  await current.fill(PASSWORD);
  await page.getByRole("button", { name: "Show password", exact: true }).first().click();
  await expect(next).toHaveAttribute("type", "text");
  await expect(repeat).toHaveAttribute("type", "password");
  await expect(current).toHaveAttribute("type", "password");
  await expect(next).toHaveValue("new-password");
});
