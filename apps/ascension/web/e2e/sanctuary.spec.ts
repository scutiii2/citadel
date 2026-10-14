import { readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';
import { CATALOG, PROFILE, ascendedInfo, ownedAscended, battleView, fighter } from '../src/api/AscensionClient.fixtures';
import { installFakeApi } from './fakeApi';

const ids = ['twoychi', 'striker', 'bruiser', 'guardian', 'scout', 'channeler', 'sentinel', 'cindrax'];
const config = JSON.parse(readFileSync(new URL('../../configs/ascension_catalog.json', import.meta.url), 'utf8'));

async function prepare(page: Page) {
  const api = await installFakeApi(page);
  const characters = ids.map(id => {
    const spec = JSON.parse(readFileSync(new URL(`../../ascended/${id}/catalog.json`, import.meta.url), 'utf8'));
    return ascendedInfo(id, { ...spec, art: { main_card: `/ascended/${id}/sprite_main_card.webp`, preview_card: `/ascended/${id}/sprite_preview_card.webp`, battle: `/ascended/${id}/sprite_battle.webp`, focus: 50, focus_preview: 50, animation: null } });
  });
  api.catalog = { ...CATALOG, ascendeds: characters, tiers: config.tiers, personalities: config.personalities };
  api.ascension.profile = { ...structuredClone(PROFILE), insignia: 2546, essences: { common: 38, rare: 18, unique: 12 }, squad: ids.slice(0, 5), ascendeds: ids.slice(0, 7).map((id, i) => ownedAscended(id, { name: characters[i]!.name, in_squad: i < 5, level: i === 0 ? 9 : 4, tier_id: i === 0 ? 'unique' : i < 3 || i > 4 ? 'rare' : 'common', default_preset_slot: 3 })) };
  api.encounter = { ...api.encounter, ascended_id: 'guardian', name: 'Guardian', level: 10, tier_id: 'common' };
  api.shop = { ...api.shop, offers: ids.slice(0, 5).map((id, slot) => ({ slot, ascended_id: id, tier_id: slot === 0 ? 'royal' : slot < 3 ? 'rare' : 'common', price: slot === 0 ? 2352 : 230, copies_granted: slot === 0 ? 4 : 1, stock: 3, left: 3, owned: true, owned_copies: 1 })) };
  await page.route('**/ascension/ascendeds/*/presets/*', route => route.fulfill({ json: { ascended_id: 'twoychi', slot: 3, instance_ids: ['p1', 'p2', 'p3'], personalities: [{ id: 'p1', type: 'AGGRESSIVE', tier: 2 }, { id: 'p2', type: 'RECKLESS', tier: 1 }, { id: 'p3', type: 'BOLD', tier: 1 }] } }));
  return api;
}

async function fits(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(await page.locator('.main').evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
}

for (const width of [1440, 768, 375]) {
  test(`sanctuary collection, shop and preparation at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const api = await prepare(page);
    await page.goto('/#ticket=e2e-launch');
    await expect(page.getByRole('heading', { name: 'Your Ascended', exact: true })).toBeVisible();
    await expect(page.locator('.wallet')).toHaveText('2,546');
    const header = page.locator('.mast');
    await expect(header.getByRole('button', { name: /Tavern/ })).toBeDisabled();
    expect(await header.locator('.wallet').evaluate(el => el.nextElementSibling?.classList.contains('shop-action'))).toBe(true);
    if (width < 1000) {
      await expect(header.locator('.tab-label').first()).toBeHidden();
      await expect(header.locator('.nav-label').first()).toBeHidden();
    } else await expect(header.locator('.tab-label').first()).toBeVisible();
    await fits(page);
    await page.screenshot({ path: info.outputPath(`collection-${width}.png`) });
    await header.getByRole('button', { name: 'Shop', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Shop', exact: true })).toBeVisible();
    await page.locator('[data-tier="common"] button[data-add]').click();
    await fits(page);
    await page.locator('.main').evaluate(el => { el.scrollTop = 0; });
    await page.screenshot({ path: info.outputPath(`shop-${width}.png`) });
    if (width < 1000) {
      await page.locator('.basket-toggle').click();
      await expect(page.locator('dialog.basket-panel')).toBeVisible();
      await page.locator('dialog.basket-panel input[type=number]').fill('2');
      await page.screenshot({ path: info.outputPath(`basket-${width}.png`) });
      await page.keyboard.press('Escape');
      await expect(page.locator('dialog.basket-panel')).not.toBeVisible();
      await page.locator('.basket-toggle').click();
      await expect(page.locator('dialog.basket-panel input[type=number]')).toHaveValue('2');
      await page.keyboard.press('Escape');
    }
    await header.getByRole('tab', { name: 'Battle', exact: true }).click();
    await page.getByRole('button', { name: 'Look for a wild Ascended', exact: true }).click();
    await page.screenshot({ path: info.outputPath(`encounter-${width}.png`) });
    await page.getByRole('button', { name: 'Fight', exact: true }).click();
    await expect(page.locator('select[name=preset]')).toHaveValue('3');
    await expect(page.locator('.battle-traits')).toContainText('Aggressive');
    await fits(page);
    await page.screenshot({ path: info.outputPath(`preparation-${width}.png`) });
    await page.getByRole('button', { name: 'Begin battle', exact: true }).scrollIntoViewIfNeeded();
    await expect(page.getByRole('button', { name: 'Begin battle', exact: true })).toBeEnabled();
    expect(api.unexpected).toEqual([]);
  });
}

for (const width of [1440, 375]) {
  test(`battle outcomes remain readable at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const api = await prepare(page);
    api.ascension.profile!.active_battle = 'b1';
    for (const kind of ['won', 'captured', 'forfeited'] as const) {
      api.battle = battleView({ mode: 'manual', status: 'terminal', phase: 'terminal', player: fighter('twoychi', { name: 'Twoychi', tier_id: 'unique' }), wild: fighter('guardian'), result: kind === 'forfeited' ? { kind } : { kind, xp: 240, insignia: 120, essence: 3, essence_tier_id: 'unique', ...(kind === 'captured' ? { copies_granted: 3, tier_id: 'common', awarded_index: 1, revealed_personalities: [{ id: 'p1', type: 'BOLD', tier: 2 }, { id: 'p2', type: 'SUPPORTIVE', tier: 2 }] } : {}), squad_xp: ids.slice(1, 5).map(id => ({ ascended_id: id, name: id, xp: 30, level_before: 4, level_after: 4 })) } });
      await page.goto('/#ticket=e2e-launch');
      await expect(page.locator('.battle-result')).toBeVisible();
      await fits(page);
      await page.screenshot({ path: info.outputPath(`${kind}-${width}.png`) });
      await page.getByRole('button', { name: 'Back to encounters', exact: true }).scrollIntoViewIfNeeded();
      await expect(page.getByRole('button', { name: 'Back to encounters', exact: true })).toBeEnabled();
      await page.goto('about:blank');
    }
    expect(api.unexpected).toEqual([]);
  });
}
