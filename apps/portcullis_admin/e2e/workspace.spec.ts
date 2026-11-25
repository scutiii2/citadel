import { expect, test, type Page } from "@playwright/test";
import { installFakeApi, ACCOUNT, PASSWORD } from "./workspaceFakeApi.ts";

async function flipSwitch(page: Page, name: string): Promise<void> {
  await page.locator("label").filter({ has: page.getByRole("switch", { name }) }).click();
}

// Log in directly to the moved workspace page.
async function logInAdmin(page: Page): Promise<void> {
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Username").fill(ACCOUNT.username);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
}

test("an administrator deletes an account from the Danger zone by typing its name", async ({ page }) => {
  const api = await installFakeApi(page);
  await logInAdmin(page);
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page).toHaveURL(/\/overview/);
  await page.getByRole('navigation', { name: 'Admin sections' }).getByRole('link', { name: 'Users', exact: true }).click();

  // Open maria's drawer: Delete user is in its own Danger zone, not among the edit buttons.
  await page.getByRole("row").filter({ hasText: "maria" }).click();
  const zone = page.locator(".danger-zone");
  await expect(zone).toContainText("Danger zone");
  await expect(zone.getByRole("button", { name: "Delete user" })).toBeVisible();

  // Protected accounts offer no Danger zone at all.
  await page.getByRole('dialog', { name: 'User maria', exact: true }).getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole("row").filter({ hasText: "ada" }).click();
  await expect(page.locator(".danger-zone")).toHaveCount(0);
  await page.getByRole('dialog', { name: 'User ada', exact: true }).getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole("row").filter({ hasText: "maria" }).click();

  await zone.getByRole("button", { name: "Delete user" }).click();
  const dialog = page.getByRole("dialog", { name: "Delete user" });
  await expect(dialog).toContainText("Delete 'maria' permanently?");
  const field = dialog.getByRole("textbox");
  const confirm = dialog.getByRole("button", { name: "Delete" });
  await expect(field).toBeFocused();
  await expect(confirm).toBeDisabled();

  // A wrong name keeps it locked; the right one unlocks it.
  await page.keyboard.type("mari");
  await expect(confirm).toBeDisabled();
  expect(api.accounts.has(2)).toBe(true);
  await page.keyboard.type("a");
  await expect(confirm).toBeEnabled();
  await confirm.click();

  await expect.poll(() => api.accounts.has(2)).toBe(false);
  await expect(page.getByRole("row").filter({ hasText: "maria" })).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: "joe" })).toBeVisible();

  // The fake knew every request the page made.
  expect(api.unexpected).toEqual([]);
});

test("deleting a role: one that accounts hold needs its name typed, an unused one does not", async ({ page }) => {
  const api = await installFakeApi(page);
  await logInAdmin(page);
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await page.getByRole('navigation', { name: 'Admin sections' }).getByRole('link', { name: 'Roles & permissions', exact: true }).click();
  const roleRow = (name: string) => page.locator("tbody .admin-row-button").filter({ hasText: name });
  const closeDrawer = () => page.locator("dialog[open]").getByRole("button", { name: "Close", exact: true }).click();
  await expect(roleRow("Member")).toBeVisible();

  // The protected Administrator role has no Danger zone.
  await roleRow("Administrator").click();
  await expect(page.locator(".danger-zone")).toHaveCount(0);
  await closeDrawer();

  // Member is held by an account: its name must be typed.
  await roleRow("Member").click();
  const zone = page.locator(".danger-zone");
  await expect(zone).toContainText("Danger zone");
  await zone.getByRole("button", { name: "Delete role" }).click();
  const dialog = page.getByRole("dialog", { name: "Delete role", exact: true });
  await expect(dialog).toContainText("Delete role 'Member'? It is removed from 1 user.");
  const confirm = dialog.getByRole("button", { name: "Delete" });
  await expect(dialog.getByRole("textbox")).toBeFocused();
  await expect(confirm).toBeDisabled();
  await page.keyboard.type("Membe");
  await expect(confirm).toBeDisabled();
  await page.keyboard.type("r");
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect.poll(() => api.roles.has(2)).toBe(false);
  await expect(roleRow("Member")).toHaveCount(0);

  // Ops holds no account: no text to type, the button is ready at once.
  await roleRow("Ops").click();
  await page.locator(".danger-zone").getByRole("button", { name: "Delete role" }).click();
  await expect(dialog).toContainText("It is removed from 0 users.");
  await expect(dialog.getByRole("textbox")).toHaveCount(0);
  await dialog.getByRole("button", { name: "Delete" }).click();
  await expect.poll(() => api.roles.has(3)).toBe(false);
  await expect(roleRow("Ops")).toHaveCount(0);

  expect(api.unexpected).toEqual([]);
});

test('overview shortcuts retain account filters across reload and legacy links open their new page', async ({ page }) => {
  const api = await installFakeApi(page);
  await logInAdmin(page);
  await page.locator('.attention').getByRole('link', { name: 'Review', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/accounts\?status=unverified/);
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.locator('tbody')).toContainText('joe');
  await page.reload();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.goto('/admin?tab=roles&source=bookmark');
  await expect(page).toHaveURL(/\/admin\/roles\?source=bookmark/);
  await expect(page.getByRole('heading', { name: 'Roles & permissions', level: 1 })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Admin sections' }).getByRole('link', { name: 'Roles & permissions', exact: true })).toHaveAttribute('aria-current', 'page');
  expect(api.unexpected).toEqual([]);
});

test('a role viewer sees only the permitted pages and cannot change permissions', async ({ page }) => {
  const api = await installFakeApi(page, ['roles.view']);
  await logInAdmin(page);
  const nav = page.getByRole('navigation', { name: 'Admin sections' });
  await expect(nav.getByRole('link')).toHaveCount(2);
  await expect(page.locator('.stats')).toHaveCount(0);
  await nav.getByRole('link', { name: 'Roles & permissions', exact: true }).click();
  await expect(page.locator('[data-test="new-role"]')).toHaveCount(0);
  await page.locator('tbody .admin-row-button').filter({ hasText: 'Member' }).click();
  for (const control of await page.getByRole('switch').all()) await expect(control).toBeDisabled();
  await page.goto('/admin/settings');
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole('heading', { name: 'Overview', level: 1 })).toBeVisible();
  expect(api.unexpected).toEqual([]);
});

test('Invite member opens a drawer, keeps ?create out of the address and confirms delivery', async ({ page }) => {
  const api = await installFakeApi(page);
  await logInAdmin(page);
  await page.getByRole('link', { name: 'Invite member', exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/invites$/);
  const dialog = page.getByRole('dialog', { name: 'Invite member', exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByRole('textbox', { name: 'Email of the new member' }).fill('new@example.com');
  await dialog.getByRole('button', { name: 'Send invite', exact: true }).click();
  await expect(dialog).toContainText('Invitation sent to new@example.com.');
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  expect(api.unexpected).toEqual([]);
});

test('admin pages fit desktop, tablet, and mobile in both themes', async ({ page }) => {
  const api = await installFakeApi(page);
  await logInAdmin(page);
  for (const color of ['light', 'dark']) {
    await page.evaluate((scheme) => { localStorage.setItem('ember_admin.theme', scheme); }, color);
    for (const width of [1280, 768, 375]) {
      await page.setViewportSize({ width, height: 812 });
      for (const route of ['/overview', '/admin/accounts', '/admin/roles', '/admin/invites', '/admin/settings']) {
        await page.goto(route);
        await expect(page.locator('header.portcullis-header h1')).toBeVisible();
        await expect(page.locator('#portcullis-sidebar')).toHaveCount(1);
        if (width >= 768) await expect(page.getByRole('navigation', { name: 'Admin sections' })).toBeVisible();
        await expect(page.locator('#portcullis-sidebar a[aria-current="page"]')).toHaveCount(1);
        expect(await page.evaluate<string>('document.documentElement.style.colorScheme')).toBe(color);
        expect(await page.evaluate<boolean>('document.documentElement.scrollWidth <= window.innerWidth')).toBe(true);
      }
    }
  }
  expect(api.unexpected).toEqual([]);
});


test("role edits save through the drawer footer after confirmation, discard on Cancel, and affected accounts load on demand", async ({ page }) => {
  const api = await installFakeApi(page);
  await logInAdmin(page);
  await page.getByRole('navigation', { name: 'Admin sections' }).getByRole('link', { name: 'Roles & permissions', exact: true }).click();
  await page.locator('tbody .admin-row-button').filter({ hasText: 'Member' }).click();
  const drawer = page.getByRole('dialog', { name: 'Role Member', exact: true });
  await drawer.getByRole('button', { name: 'View affected users' }).click();
  await expect(drawer.locator('.affected-accounts')).toContainText('maria');
  await expect(drawer.locator('.affected-accounts')).not.toContainText('ada');

  // Switches are read-only until Edit; Cancel asks before dropping the draft.
  await expect(page.getByRole('switch', { name: 'chat.use', exact: true })).toBeDisabled();
  await drawer.getByRole('button', { name: 'Edit', exact: true }).click();
  await flipSwitch(page, 'chat.use');
  expect(api.roles.get(2)!.permissions).toContain('chat.use');
  await drawer.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.getByRole('dialog', { name: 'Discard changes?' }).getByRole('button', { name: 'Discard changes' }).click();
  expect(api.roles.get(2)!.permissions).toContain('chat.use');
  await drawer.getByRole('button', { name: 'Edit', exact: true }).click();
  await expect(page.getByRole('switch', { name: 'chat.use', exact: true })).toBeChecked();

  await flipSwitch(page, 'chat.use');
  await drawer.getByRole('button', { name: 'Save changes', exact: true }).click();
  await page.getByRole('dialog', { name: 'Save changes?' }).getByRole('button', { name: 'Save changes' }).click();
  await expect.poll(() => api.roles.get(2)!.permissions.includes('chat.use')).toBe(false);
  await expect(drawer.getByRole('button', { name: 'Edit', exact: true })).toBeVisible();
  expect(api.unexpected).toEqual([]);
});

test('permission switch appearance follows repeated pointer and keyboard changes', async ({ page }) => {
  const api = await installFakeApi(page);
  await logInAdmin(page);
  await page.getByRole('navigation', { name: 'Admin sections' }).getByRole('link', { name: 'Roles & permissions', exact: true }).click();
  await page.locator('tbody .admin-row-button').filter({ hasText: 'Member' }).click();
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  const control = page.getByRole('switch', { name: 'chat.use', exact: true });
  await expect(control).toBeChecked();
  const on = await page.evaluate("getComputedStyle(document.querySelector('input[aria-label=\"chat.use\"] + .track')).backgroundColor");
  await flipSwitch(page, 'chat.use');
  await expect(control).not.toBeChecked();
  await page.waitForTimeout(200);
  const off = await page.evaluate("getComputedStyle(document.querySelector('input[aria-label=\"chat.use\"] + .track')).backgroundColor");
  expect(off).not.toEqual(on);
  await control.focus();
  await page.keyboard.press('Space');
  await expect(control).toBeChecked();
  expect(api.roles.get(2)!.permissions).toContain('chat.use');
  expect(api.unexpected).toEqual([]);
});

test('an invites administrator can use the overview and sees only available destinations', async ({ page }) => {
  const api = await installFakeApi(page, ['invites.manage']);
  await logInAdmin(page);
  await expect(page.locator('.destination')).toHaveCount(1);
  await expect(page.locator('.destination')).toHaveAttribute('href', '/admin/invites');
  await expect(page.locator('.destination p')).not.toBeEmpty();
  expect(api.unexpected).toEqual([]);
});

test('the drawer expands, scrolls its own body and keeps the footer reachable', async ({ page }) => {
  const api = await installFakeApi(page);
  await logInAdmin(page);
  await page.getByRole('navigation', { name: 'Admin sections' }).getByRole('link', { name: 'Roles & permissions', exact: true }).click();
  await page.locator('tbody .admin-row-button').filter({ hasText: 'Member' }).click();
  const drawer = page.getByRole('dialog', { name: 'Role Member', exact: true });
  await drawer.getByRole('button', { name: 'Edit', exact: true }).click();
  for (const width of [1280, 768, 375]) {
    await page.setViewportSize({ width, height: 600 });
    const body = drawer.locator('.drawer-body');
    expect(await body.evaluate((el) => getComputedStyle(el).overflowY)).toBe('auto');
    expect(await page.evaluate<boolean>('document.documentElement.scrollHeight <= window.innerHeight')).toBe(true);
    const footer = (await drawer.locator('.drawer-footer').boundingBox())!;
    expect(footer.y + footer.height).toBeLessThanOrEqual(600);
    const normal = (await drawer.boundingBox())!.width;
    await drawer.getByRole('button', { name: 'Expand drawer' }).click();
    const wide = (await drawer.boundingBox())!.width;
    expect(wide).toBeGreaterThanOrEqual(normal);
    expect(Math.abs(wide - (width < 768 ? width : Math.max(normal, width * 0.9)))).toBeLessThanOrEqual(2);
    await drawer.getByRole('button', { name: 'Expand drawer' }).click();
    expect((await drawer.boundingBox())!.width).toBe(normal);
  }
  expect(api.unexpected).toEqual([]);
});
