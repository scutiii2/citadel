import { mount, flushPromises } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { expect, it, vi } from 'vitest';
import TrialsPanel from './TrialsPanel.vue';
import { CATALOG, PROFILE } from '../api/AscensionClient.fixtures';
import { useAscensionStore } from '../stores/ascension';
import type { ActivityDefinitions } from '../api/AscensionClient';
const mock = vi.hoisted(() => ({ trialProgress:vi.fn(), prepareTrial:vi.fn(), preset:vi.fn() }));
vi.mock('../api/AscensionClient', () => ({ useAscensionClient:() => mock }));

it('shows all types, explains empty Trials, and gates later stages', async () => {
  setActivePinia(createPinia());
  const store=useAscensionStore(); store.profile=PROFILE;
  const stages=[1,2,3,4].map(stage=>({stage,ascended_id:'guardian',tier_id:'common',level:3,cleared:false,unlocked:stage===1,first_clear:true}));
  const definitions: ActivityDefinitions={hunts:[],trial_types:['pure','abyss','divine','crimson','enchant','synthetic'],trial_stages:stages,expeditions:{durations_hours:[2,4,8],xp_per_hour:100,insignia_per_hour:25},max_hunt_penalty:.75,trial_first_clear_multiplier:2};
  store.catalog={...CATALOG,activities:definitions};
  mock.trialProgress.mockResolvedValue({trials:definitions.trial_types.map(type_id=>({type_id,stages}))});
  mock.prepareTrial.mockImplementation(async (type_id:string,stage:number)=>({type_id,stage,unlocked:stage===1,first_clear:true,eligible_ascended_ids:type_id==='enchant'?['guardian']:[],reason:type_id==='enchant'?null:'No eligible Ascended',opponent:{ascended_id:'guardian',name:'Guardian',tier_id:'common',level:3,overall:222}}));
  mock.preset.mockResolvedValue({instance_ids:[],personalities:[]});
  const wrapper=mount(TrialsPanel); await flushPromises();
  expect(wrapper.findAll('.trial-types button')).toHaveLength(6);
  expect(wrapper.findAll('.trial-stages button')[1]!.attributes('disabled')).toBeDefined();
  expect(wrapper.text()).toContain('First-clear rewards ×2');
  expect(wrapper.find("select[name='limit']").exists()).toBe(false);
  await wrapper.findAll('.trial-types button')[0]!.trigger('click'); await flushPromises();
  expect(wrapper.text()).toContain('No eligible Ascended');
  expect(wrapper.find('.begin-battle').exists()).toBe(false);
  wrapper.unmount();
});
