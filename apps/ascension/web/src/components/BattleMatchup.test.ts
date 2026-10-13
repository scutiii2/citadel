import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { usePlaybackStore } from "../stores/playback";
import { ENCOUNTER, ascendedInfo, ownedAscended } from "../api/AscensionClient.fixtures";
import BattleMatchup from "./BattleMatchup.vue";

vi.mock('../api/AscensionClient', () => ({ useAscensionClient: () => ({}) }));

const props = () => ({
  player: ownedAscended("guardian", { level: 5, tier_id: "rare" }),
  playerInfo: ascendedInfo("guardian"),
  wild: ENCOUNTER,
  wildInfo: ascendedInfo("bruiser"),
  playerMultiplier: 1.6,
});

describe("BattleMatchup", () => {
  beforeEach(() => setActivePinia(createPinia()));
  it("shows your fighter left and opponent right on the battle stage with their tiers, levels and stats", () => {
    const wrapper = mount(BattleMatchup, { props: props() });
    expect(wrapper.find(".player .ascended-name").text()).toBe("Guardian");
    expect(wrapper.find(".wild .ascended-name").text()).toBe("Bruiser");
    expect(wrapper.findAll('.fighter').map(f => f.classes().includes('player'))).toEqual([true, false]);
    expect(wrapper.find(".player .head small").text()).toBe("Lv. 5");
    expect(wrapper.find(".wild .head small").text()).toBe("Lv. 4");
    expect(wrapper.find(".player .em-tier").text()).toBe('Rare');
    expect(wrapper.find(".player p.hp").text()).toBe('HP 192 / 192');
    expect(wrapper.find(".player .stats").text()).toBe('Power 22 · Speed 22');
    expect(wrapper.find('.arena').classes()).toContain('preview');
    expect(wrapper.find('.player .card').exists()).toBe(false);
    expect(wrapper.find(".wild .stats").exists()).toBe(true);
    expect(wrapper.text()).toContain("Opponent personalities stay hidden until capture");
  });

  it("keeps the preview at full health without effects from the previous battle", () => {
    const playback = usePlaybackStore();
    playback.hp = { player: 5, wild: 3 };
    playback.busy = true;
    playback.fx = { player: 'lunge', wild: 'hit' };
    const wrapper = mount(BattleMatchup, { props: props() });
    expect(wrapper.find('.player p.hp').text()).toBe('HP 192 / 192');
    expect(wrapper.find('.arena').classes()).not.toContain('playing');
    expect(wrapper.find('.fx-lunge, .fx-hit').exists()).toBe(false);
  });

  it("does not invent a fighter when no ready member is selected", () => {
    const wrapper = mount(BattleMatchup, { props: { ...props(), player: null, playerInfo: null } });
    expect(wrapper.find(".player").text()).toContain("Choose a fighter");
    expect(wrapper.find(".player .card").exists()).toBe(false);
    expect(wrapper.find(".wild .ascended-name").text()).toBe("Bruiser");
  });
});
