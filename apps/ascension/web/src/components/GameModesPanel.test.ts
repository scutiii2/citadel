import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { expect, it, vi } from 'vitest';
import GameModesPanel from './GameModesPanel.vue';
import { useAscensionStore } from '../stores/ascension';
import { CATALOG, PROFILE } from '../api/AscensionClient.fixtures';

vi.mock('../api/AscensionClient', () => ({ useAscensionClient: () => ({}) }));

it('offers three modes inside the existing Battle content', () => {
  setActivePinia(createPinia());
  const store = useAscensionStore();
  store.catalog = CATALOG; store.profile = PROFILE;
  const wrapper = mount(GameModesPanel);
  expect(wrapper.text()).toContain('Wild Hunts');
  expect(wrapper.text()).toContain('Ascension Trials');
  expect(wrapper.text()).toContain('Expeditions');
  expect(wrapper.find('header.mast').exists()).toBe(false);
});
