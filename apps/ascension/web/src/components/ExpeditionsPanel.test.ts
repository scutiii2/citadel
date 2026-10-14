import { mount, flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { afterEach, expect, it, vi } from 'vitest';
import ExpeditionsPanel from './ExpeditionsPanel.vue';
import AscendedPreviewCard from './AscendedPreviewCard.vue';
import AscendedProgression from './AscendedProgression.vue';
import { CATALOG, PROFILE, ownedAscended } from '../api/AscensionClient.fixtures';
import { useAscensionStore } from '../stores/ascension';
import type { ExpeditionStatus } from '../api/AscensionClient';
const mock = vi.hoisted(() => ({ expedition: vi.fn() }));
vi.mock('../api/AscensionClient', () => ({ useAscensionClient: () => mock }));
afterEach(() => vi.restoreAllMocks());

it('uses the unchanged preview card and prevents early claim despite wall clock skew', async () => {
  setActivePinia(createPinia());
  vi.spyOn(performance, 'now').mockReturnValueOnce(1000).mockReturnValue(2000);
  const store = useAscensionStore(); store.catalog = CATALOG; store.profile = PROFILE;
  const status: ExpeditionStatus = { server_now: 100, expedition: { id:'x', ascended_id:'guardian', started_at:100, ends_at:7300, duration_hours:2, xp_reward:200, insignia_reward:50, state:'on_expedition', can_claim:false, seconds_remaining:7200 } };
  mock.expedition.mockResolvedValue(status);
  const wrapper = mount(ExpeditionsPanel); await flushPromises();
  store.expeditionObservedAt = 3000;
  await flushPromises();
  vi.spyOn(Date, 'now').mockReturnValue(9999999999999);
  expect(wrapper.findComponent(AscendedPreviewCard).exists()).toBe(true);
  expect(wrapper.find('.expedition-timer').text()).toBe('2:00:00');
  expect(wrapper.text()).toContain('Squad, upgrades, and loadout changes are locked');
  expect(wrapper.findAll('button').find(b => b.text() === 'Claim & Return')!.attributes('disabled')).toBeDefined();
  wrapper.unmount();
});

it('disables progression during an expedition even if stale eligibility flags say yes', () => {
  const wrapper = mount(AscendedProgression, { props: { ascended: ownedAscended('guardian', { on_expedition:true, can_star_up:true, can_tier_up:true }), info: CATALOG.ascendeds[0]!, essence:100, busy:false, message:'' } });
  expect(wrapper.text()).toContain('expedition');
  expect(wrapper.findAll('button').every(b => b.attributes('disabled') !== undefined)).toBe(true);
});
