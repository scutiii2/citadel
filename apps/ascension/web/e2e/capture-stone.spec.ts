import { expect, test } from '@playwright/test';
import { PROFILE, battleView, fighter } from '../src/api/AscensionClient.fixtures';
import { installFakeApi } from './fakeApi';

const scenarios = [1440, 375].flatMap(width => [true, false].map(success => ({ width, success })));
for (const { width, success } of scenarios) {
    test(`engraved stone ${success ? 'seals' : 'breaks'} at ${width}px`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 1000 });
      const api = await installFakeApi(page);
      api.ascension.profile = { ...structuredClone(PROFILE), active_battle: 'b1' };
      api.battle = battleView({ mode: 'manual', emblems: { rare: 2 }, wild: fighter('striker', { tier_id: 'rare' }) });
      await page.route('**/ascension/battles/b1/actions', async route => {
        expect(route.request().postDataJSON().action).toMatchObject({ kind: 'catch', emblem_tier: 'rare' });
        api.battle = { ...api.battle!, round: 2, revision: 2, history: [{ round: 1, actions: { player: ['catch', 'INTERCEPT'], wild: ['attack', 'ATTACK'] }, events: [{ type: 'capture_attempt', side: 'player', emblem: 'rare', chance: 0.6, success }] }] };
        await route.fulfill({ json: api.battle });
      });
      await page.goto('/#ticket=e2e-launch');
      await expect(page.locator('.action.catch')).toBeVisible();
      await page.clock.install();
      await page.clock.pauseAt(new Date());
      await page.locator('.action.catch').click();
      await page.getByRole('dialog', { name: 'Throw which EMBLEM?' }).getByRole('button', { name: /Rare/ }).click();
      const stone = page.locator('.wild .em-capture-stone');
      await expect(stone).toHaveClass(/ball-throw/);
      await expect(stone.locator('.stone-whole')).toHaveJSProperty('naturalWidth', 256);
      await page.clock.runFor(650);
      await expect(stone).toHaveClass(/ball-absorb/);
      await expect(stone.locator('.capture-flow i')).toHaveCount(8);
      await page.clock.runFor(200);
      // CSS compositor time is independent of mocked timers. Freeze the rendered frame.
      await page.locator('.arena').evaluate(el => el.getAnimations({ subtree: true }).forEach(animation => { animation.pause(); animation.currentTime = 200; }));
      await page.screenshot({ path: info.outputPath(`absorb-${width}.png`) });
      await page.clock.runFor(400);
      await expect(stone).toHaveClass(/ball-wobble/);
      await expect(page.locator('.wild .sprite')).toHaveClass(/concealed/);
      await page.clock.runFor(800 + 900 + 1000);
      await expect(stone).toHaveClass(/ball-still/);
      await page.clock.runFor(600);
      await expect(stone).toHaveClass(success ? /ball-caught/ : /ball-open/);
      if (success) await expect(page.locator('.wild .sprite')).toHaveClass(/concealed/);
      else {
        await expect(stone.locator('.stone-fragment')).toHaveCount(2);
        await expect(page.locator('.wild .sprite')).not.toHaveClass(/concealed/);
      }
      await page.clock.runFor(250);
      await page.locator('.arena').evaluate(el => el.getAnimations({ subtree: true }).forEach(animation => { animation.pause(); animation.currentTime = 250; }));
      await page.screenshot({ path: info.outputPath(`${success ? 'sealed' : 'broken'}-${width}.png`) });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.clock.runFor(800);
      await expect(stone).toHaveCount(0);
      await expect(page.locator('.action.catch')).toBeEnabled();
      expect(api.unexpected).toEqual([]);
    });
}
