import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { ENCOUNTER, ascendedInfo, ownedAscended } from "../api/AscensionClient.fixtures";
import BattleMatchup from "./BattleMatchup.vue";

const props = () => ({
  player: ownedAscended("guardian", { level: 5, tier_id: "rare" }),
  playerInfo: ascendedInfo("guardian"),
  wild: ENCOUNTER,
  wildInfo: ascendedInfo("bruiser"),
  playerMultiplier: 1.6,
});

describe("BattleMatchup", () => {
  it("shows both fighters as preview cards with their own tiers, levels and stats", () => {
    const wrapper = mount(BattleMatchup, { props: props() });
    expect(wrapper.find(".player .ascended-name").text()).toBe("Guardian");
    expect(wrapper.find(".wild .ascended-name").text()).toBe("Bruiser");
    expect(wrapper.find(".player .level").text()).toBe("Lv 5");
    expect(wrapper.find(".wild .level").text()).toBe("Lv 4");
    expect(wrapper.find(".player .card").attributes("style")).toContain("--em-tier-rare");
    expect(wrapper.findAll(".player .stats dd").map(s => s.text())).toEqual(["192", "22", "22"]);
    expect(wrapper.find(".wild .stats").exists()).toBe(true);
    expect(wrapper.text()).toContain("Opponent personalities stay hidden until capture");
  });

  it("does not invent a fighter when no ready member is selected", () => {
    const wrapper = mount(BattleMatchup, { props: { ...props(), player: null, playerInfo: null } });
    expect(wrapper.find(".player").text()).toContain("Choose a fighter");
    expect(wrapper.find(".player .card").exists()).toBe(false);
    expect(wrapper.find(".wild .ascended-name").text()).toBe("Bruiser");
  });
});
